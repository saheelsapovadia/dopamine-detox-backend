"""
Task Sync Worker (Write-Behind)
================================

Background asyncio worker that consumes task mutations from a Redis Stream
(``stream:tasks:sync``) and persists them to PostgreSQL.

Lifecycle:
    1. ``start()`` is called during the FastAPI lifespan startup.
    2. The worker creates a consumer group (idempotent) and enters
       an infinite read loop (``_process_loop``).
    3. ``stop()`` is called during shutdown — it signals the loop to
       exit and drains remaining messages.

Retry / DLQ:
    - On a transient DB error the message is NACKed (left pending)
      and retried on the next iteration.
    - After ``MAX_RETRIES`` delivery attempts the message is moved to
      a dead-letter stream (``stream:tasks:dlq``) and ACKed.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime, timezone
from typing import Any, Optional
import uuid

from sqlalchemy import delete, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session_factory
from app.models.task import (
    Task,
    TaskCategory,
    TaskIconType,
    TaskPriority,
    TaskStatus,
)
from app.services.cache import get_redis

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STREAM_KEY = "stream:tasks:sync"
DLQ_STREAM = "stream:tasks:dlq"
CONSUMER_GROUP = "sync-workers"
CONSUMER_NAME = "worker-1"
MAX_RETRIES = 5
BLOCK_MS = 200  # how long XREADGROUP blocks before returning empty
BATCH_SIZE = 50  # max messages per XREADGROUP call


# ---------------------------------------------------------------------------
# Mapping helpers  (API camelCase dict  →  DB column values)
# ---------------------------------------------------------------------------

def _api_to_db_fields(task: dict) -> dict:
    """Convert an API-format task dict to a dict of DB column values."""
    fields: dict[str, Any] = {}
    if "id" in task:
        fields["task_id"] = uuid.UUID(task["id"])
    if "userId" in task:
        fields["user_id"] = uuid.UUID(task["userId"])
    if "title" in task:
        fields["title"] = task["title"]
    if "subtitle" in task:
        fields["subtitle"] = task["subtitle"]
    if "category" in task:
        fields["category"] = TaskCategory(task["category"])
    if "priority" in task:
        fields["priority"] = TaskPriority(task["priority"])
    if "durationMins" in task:
        fields["duration_mins"] = task["durationMins"]
    if "iconType" in task:
        fields["icon_type"] = TaskIconType(task["iconType"])
    if "status" in task:
        fields["status"] = TaskStatus(task["status"])
    if "date" in task and task["date"] is not None:
        fields["due_date"] = (
            date.fromisoformat(task["date"])
            if isinstance(task["date"], str)
            else task["date"]
        )
    if "orderIndex" in task:
        fields["order_index"] = task["orderIndex"]
    return fields


# ---------------------------------------------------------------------------
# TaskSyncWorker
# ---------------------------------------------------------------------------

class TaskSyncWorker:
    """Background worker that drains the task sync stream to PostgreSQL."""

    def __init__(self) -> None:
        self._running = False
        self._task: Optional[asyncio.Task] = None

    # -- lifecycle ---------------------------------------------------------

    async def start(self) -> None:
        """Create consumer group and start the processing loop."""
        try:
            client = await get_redis()
            # XGROUP CREATE is idempotent when using MKSTREAM
            try:
                await client.xgroup_create(
                    STREAM_KEY, CONSUMER_GROUP, id="0", mkstream=True,
                )
                logger.info("Created consumer group '%s'", CONSUMER_GROUP)
            except Exception:
                # Group already exists — that's fine.
                pass

            self._running = True
            self._task = asyncio.create_task(self._process_loop())
            logger.info("TaskSyncWorker started")
        except Exception as exc:
            logger.error("TaskSyncWorker failed to start: %s", exc)

    async def stop(self) -> None:
        """Signal the loop to stop and wait for it to finish."""
        self._running = False
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=10)
            except asyncio.TimeoutError:
                logger.warning("TaskSyncWorker did not stop in time; cancelling")
                self._task.cancel()
            except Exception:
                pass
        logger.info("TaskSyncWorker stopped")

    # -- main loop ---------------------------------------------------------

    async def _process_loop(self) -> None:
        """
        Continuously read from the stream and process messages.

        On each iteration we first claim any pending messages that have
        been idle for too long (stuck retries), then read new messages.
        """
        while self._running:
            try:
                await self._reclaim_pending()
                await self._read_and_process()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("TaskSyncWorker loop error: %s", exc)
                await asyncio.sleep(1)  # back off on unexpected errors

        # Drain pass: try to process remaining pending messages once.
        try:
            await self._reclaim_pending()
        except Exception:
            pass

    async def _read_and_process(self) -> None:
        """Read a batch of new messages and process them."""
        client = await get_redis()
        messages = await client.xreadgroup(
            CONSUMER_GROUP,
            CONSUMER_NAME,
            {STREAM_KEY: ">"},
            count=BATCH_SIZE,
            block=BLOCK_MS,
        )
        if not messages:
            return

        for _stream_name, entries in messages:
            for msg_id, fields in entries:
                await self._handle_message(client, msg_id, fields)

    async def _reclaim_pending(self) -> None:
        """
        Check for pending messages that have been delivered too many times
        and move them to the DLQ.  Also re-attempt messages that were
        NACKed (delivery count < MAX_RETRIES).
        """
        client = await get_redis()
        try:
            pending = await client.xpending_range(
                STREAM_KEY, CONSUMER_GROUP, "-", "+", count=BATCH_SIZE,
            )
        except Exception:
            return

        for entry in pending:
            msg_id = entry["message_id"]
            times_delivered = entry["times_delivered"]

            if times_delivered >= MAX_RETRIES:
                # Move to DLQ
                try:
                    raw_msgs = await client.xrange(STREAM_KEY, msg_id, msg_id)
                    if raw_msgs:
                        _, fields = raw_msgs[0]
                        fields["original_id"] = msg_id
                        fields["retries"] = str(times_delivered)
                        await client.xadd(DLQ_STREAM, fields, maxlen=5000, approximate=True)
                    await client.xack(STREAM_KEY, CONSUMER_GROUP, msg_id)
                    logger.warning(
                        "Moved message %s to DLQ after %d retries",
                        msg_id,
                        times_delivered,
                    )
                except Exception as exc:
                    logger.error("DLQ move error for %s: %s", msg_id, exc)

    # -- message handler ---------------------------------------------------

    async def _handle_message(
        self,
        client: Any,
        msg_id: str,
        fields: dict,
    ) -> None:
        """Parse and process a single stream message, ACK on success."""
        op = fields.get("op", "")
        payload_raw = fields.get("payload", "{}")
        try:
            payload = json.loads(payload_raw)
        except json.JSONDecodeError:
            logger.error("Bad JSON in message %s, ACKing to skip", msg_id)
            await client.xack(STREAM_KEY, CONSUMER_GROUP, msg_id)
            return

        try:
            await self._process_message(op, payload)
            await client.xack(STREAM_KEY, CONSUMER_GROUP, msg_id)
        except Exception as exc:
            # Leave un-ACKed for retry on next _reclaim_pending pass.
            logger.error(
                "Sync failed for %s (op=%s): %s", msg_id, op, exc,
            )

    async def _process_message(self, op: str, payload: dict) -> None:
        """Execute the DB write corresponding to *op*."""
        session_factory = get_session_factory()
        async with session_factory() as session:
            try:
                if op == "CREATE":
                    await self._sync_create(session, payload)
                elif op == "BATCH_CREATE":
                    await self._sync_batch_create(session, payload)
                elif op == "UPDATE":
                    await self._sync_update(session, payload)
                elif op == "BATCH_UPDATE":
                    await self._sync_batch_update(session, payload)
                elif op == "STATUS_UPDATE":
                    await self._sync_status_update(session, payload)
                elif op == "DELETE":
                    await self._sync_delete(session, payload)
                else:
                    logger.warning("Unknown sync op '%s', skipping", op)

                await session.commit()
            except Exception:
                await session.rollback()
                raise

    # -- individual operation handlers -------------------------------------

    async def _sync_create(self, db: AsyncSession, payload: dict) -> None:
        """INSERT a single task."""
        fields = _api_to_db_fields(payload)
        # Set timestamps from cache-generated values if present
        if "createdAt" in payload and payload["createdAt"]:
            fields["created_at"] = datetime.fromisoformat(payload["createdAt"])
        if "updatedAt" in payload and payload["updatedAt"]:
            fields["updated_at"] = datetime.fromisoformat(payload["updatedAt"])

        stmt = pg_insert(Task).values(**fields).on_conflict_do_nothing(
            index_elements=["task_id"],
        )
        await db.execute(stmt)

    async def _sync_batch_create(
        self, db: AsyncSession, payload: dict,
    ) -> None:
        """Bulk INSERT tasks."""
        tasks_data = payload.get("tasks", [])
        for task_dict in tasks_data:
            await self._sync_create(db, task_dict)

    async def _sync_update(self, db: AsyncSession, payload: dict) -> None:
        """UPDATE a single task (partial fields)."""
        task_id = payload.get("task_id") or payload.get("id")
        if not task_id:
            return
        updates = payload.get("updates", payload)
        db_fields = _api_to_db_fields(updates)
        # Remove task_id/user_id from the SET clause
        db_fields.pop("task_id", None)
        db_fields.pop("user_id", None)
        if "updatedAt" in updates and updates["updatedAt"]:
            db_fields["updated_at"] = datetime.fromisoformat(updates["updatedAt"])
        elif "updatedAt" not in db_fields:
            db_fields["updated_at"] = datetime.now(timezone.utc)

        if not db_fields:
            return

        stmt = (
            update(Task)
            .where(Task.task_id == uuid.UUID(str(task_id)))
            .values(**db_fields)
        )
        await db.execute(stmt)

    async def _sync_batch_update(
        self, db: AsyncSession, payload: dict,
    ) -> None:
        """Batch UPDATE tasks."""
        tasks_data = payload.get("tasks", [])
        for task_dict in tasks_data:
            await self._sync_update(db, task_dict)

    async def _sync_status_update(
        self, db: AsyncSession, payload: dict,
    ) -> None:
        """UPDATE only the status column."""
        task_id = payload.get("task_id") or payload.get("id")
        new_status = payload.get("status")
        if not task_id or not new_status:
            return
        updated_at = datetime.now(timezone.utc)
        if payload.get("updatedAt"):
            updated_at = datetime.fromisoformat(payload["updatedAt"])
        stmt = (
            update(Task)
            .where(Task.task_id == uuid.UUID(str(task_id)))
            .values(status=TaskStatus(new_status), updated_at=updated_at)
        )
        await db.execute(stmt)

    async def _sync_delete(self, db: AsyncSession, payload: dict) -> None:
        """DELETE a task row."""
        task_id = payload.get("task_id") or payload.get("id")
        if not task_id:
            return
        stmt = delete(Task).where(Task.task_id == uuid.UUID(str(task_id)))
        await db.execute(stmt)
