"""
Task Cache Service (Cache-First)
=================================

Redis Hash-based task cache that serves as the primary data store for reads.
Mutations are written to Redis first, then asynchronously synced to PostgreSQL
via a Redis Stream.

Redis Data Model:
    tasks:data:{user_id}:{date}   -> Hash  {task_id: JSON task dict, ...}
    tasks:meta:{user_id}:{date}   -> Hash  {total: N, completed: N}
    stream:tasks:sync             -> Stream {op, user_id, date, task_id, payload, ts}

On Redis failure every public method returns ``None`` so callers can
fall back to direct PostgreSQL access (graceful degradation).
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from app.services.cache import get_redis

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TTL_DAY = 86400  # 24 hours – auto-cleanup for old dates
_SYNC_STREAM = "stream:tasks:sync"
_SYNC_MAXLEN = 10_000  # cap stream length (approximate trimming)


# ---------------------------------------------------------------------------
# Key helpers
# ---------------------------------------------------------------------------

def _data_key(user_id: str, dt: str) -> str:
    return f"tasks:data:{user_id}:{dt}"


def _meta_key(user_id: str, dt: str) -> str:
    return f"tasks:meta:{user_id}:{dt}"


# ---------------------------------------------------------------------------
# TaskCacheService
# ---------------------------------------------------------------------------

class TaskCacheService:
    """
    Cache-first task operations backed by Redis Hashes.

    Every method is ``async`` and catches Redis errors internally,
    returning ``None`` on failure so the caller can fall back to the DB.
    """

    # ---- reads -----------------------------------------------------------

    async def get_tasks_for_date(
        self,
        user_id: uuid.UUID,
        target_date: date,
    ) -> Optional[list[dict]]:
        """
        Return all cached tasks for *user_id* on *target_date*.

        Returns ``None`` on Redis failure (caller should fall back to DB).
        Returns an empty list ``[]`` when the key exists but has no fields
        (i.e. the date has been hydrated but has no tasks).
        """
        try:
            client = await get_redis()
            key = _data_key(str(user_id), target_date.isoformat())
            raw: dict[str, str] = await client.hgetall(key)
            if not raw:
                return None  # cache miss – caller will hydrate
            # Parse values, skipping the __empty__ sentinel and any
            # non-dict entries (e.g. meta leftovers).
            tasks: list[dict] = []
            for field_key, v in raw.items():
                if field_key == "__empty__":
                    continue
                parsed = json.loads(v)
                if isinstance(parsed, dict):
                    tasks.append(parsed)
            # Sort: high priority first, then by order_index
            _priority_order = {"high": 0, "medium": 1, "low": 2}
            tasks.sort(
                key=lambda t: (
                    _priority_order.get(t.get("priority", "medium"), 1),
                    t.get("orderIndex", 0),
                ),
            )
            return tasks
        except Exception as exc:
            logger.warning("task_cache get_tasks_for_date error: %s", exc)
            return None

    async def get_task(
        self,
        user_id: uuid.UUID,
        target_date: date,
        task_id: str,
    ) -> Optional[dict]:
        """Return a single cached task dict, or ``None``."""
        try:
            client = await get_redis()
            key = _data_key(str(user_id), target_date.isoformat())
            raw = await client.hget(key, task_id)
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as exc:
            logger.warning("task_cache get_task error: %s", exc)
            return None

    async def get_high_priority_task(
        self,
        user_id: uuid.UUID,
        target_date: date,
    ) -> Optional[dict]:
        """
        Scan the tasks hash for a task with ``priority == "high"``.

        Returns the task dict if found, ``None`` otherwise.
        Also returns ``None`` on Redis failure.
        """
        try:
            client = await get_redis()
            key = _data_key(str(user_id), target_date.isoformat())
            raw: dict[str, str] = await client.hgetall(key)
            if not raw:
                return None
            for field_key, v in raw.items():
                if field_key == "__empty__":
                    continue
                task = json.loads(v)
                if isinstance(task, dict) and task.get("priority") == "high":
                    return task
            return None
        except Exception as exc:
            logger.warning("task_cache get_high_priority_task error: %s", exc)
            return None

    async def get_day_summaries(
        self,
        user_id: uuid.UUID,
        reference_date: date,
        num_days: int = 7,
    ) -> Optional[list[dict]]:
        """
        Build day-selector pill summaries for *num_days* ending at
        *reference_date* using the lightweight ``tasks:meta`` hashes.

        Returns ``None`` on Redis failure.
        """
        try:
            client = await get_redis()
            dates = [reference_date - timedelta(days=i) for i in range(num_days)]
            today = date.today()
            weekday_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

            # Pipeline: fetch all meta hashes in one round-trip
            pipe = client.pipeline(transaction=False)
            for d in dates:
                pipe.hgetall(_meta_key(str(user_id), d.isoformat()))
            results = await pipe.execute()

            summaries: list[dict] = []
            for d, meta in zip(dates, results):
                total = int(meta.get("total", 0)) if meta else 0
                completed = int(meta.get("completed", 0)) if meta else 0
                is_today = d == today
                label = "Today" if is_today else weekday_labels[d.weekday()]
                is_completed = total > 0 and completed == total

                summaries.append({
                    "date": d.isoformat(),
                    "label": label,
                    "isToday": is_today,
                    "isCompleted": is_completed,
                    "totalTasks": total,
                    "completedTasks": completed,
                })

            return summaries
        except Exception as exc:
            logger.warning("task_cache get_day_summaries error: %s", exc)
            return None

    # ---- writes ----------------------------------------------------------

    async def set_task(
        self,
        user_id: uuid.UUID,
        target_date: date,
        task_id: str,
        task_dict: dict,
    ) -> bool:
        """
        Add or overwrite a single task in the cache hash and bump the
        ``tasks:meta`` total counter.

        Returns ``False`` on Redis failure.
        """
        try:
            client = await get_redis()
            uid = str(user_id)
            dt = target_date.isoformat()
            dkey = _data_key(uid, dt)
            mkey = _meta_key(uid, dt)

            pipe = client.pipeline(transaction=False)
            pipe.hset(dkey, task_id, json.dumps(task_dict, default=str))
            pipe.hdel(dkey, "__empty__")  # remove sentinel if present
            pipe.hincrby(mkey, "total", 1)
            if task_dict.get("status") == "completed":
                pipe.hincrby(mkey, "completed", 1)
            pipe.expire(dkey, _TTL_DAY)
            pipe.expire(mkey, _TTL_DAY)
            await pipe.execute()
            return True
        except Exception as exc:
            logger.warning("task_cache set_task error: %s", exc)
            return False

    async def set_tasks_batch(
        self,
        user_id: uuid.UUID,
        target_date: date,
        tasks: list[dict],
    ) -> bool:
        """
        Bulk-insert tasks into the hash and set meta counters.

        Returns ``False`` on Redis failure.
        """
        try:
            client = await get_redis()
            uid = str(user_id)
            dt = target_date.isoformat()
            dkey = _data_key(uid, dt)
            mkey = _meta_key(uid, dt)

            pipe = client.pipeline(transaction=False)
            for t in tasks:
                pipe.hset(dkey, t["id"], json.dumps(t, default=str))
            pipe.hdel(dkey, "__empty__")  # remove sentinel if present
            # Bump meta counters
            completed = sum(1 for t in tasks if t.get("status") == "completed")
            pipe.hincrby(mkey, "total", len(tasks))
            if completed:
                pipe.hincrby(mkey, "completed", completed)
            pipe.expire(dkey, _TTL_DAY)
            pipe.expire(mkey, _TTL_DAY)
            await pipe.execute()
            return True
        except Exception as exc:
            logger.warning("task_cache set_tasks_batch error: %s", exc)
            return False

    async def update_task(
        self,
        user_id: uuid.UUID,
        target_date: date,
        task_id: str,
        updates: dict,
    ) -> Optional[dict]:
        """
        Merge *updates* into the cached task and persist to hash.

        If ``status`` changed to/from ``completed`` the meta counter is
        adjusted.  Returns the updated task dict, or ``None`` on failure.
        """
        try:
            client = await get_redis()
            uid = str(user_id)
            dt = target_date.isoformat()
            dkey = _data_key(uid, dt)
            mkey = _meta_key(uid, dt)

            raw = await client.hget(dkey, task_id)
            if raw is None:
                return None
            task = json.loads(raw)

            old_status = task.get("status")
            task.update(updates)
            task["updatedAt"] = datetime.now(timezone.utc).isoformat()
            new_status = task.get("status")

            pipe = client.pipeline(transaction=False)
            pipe.hset(dkey, task_id, json.dumps(task, default=str))

            # Adjust completed counter
            if old_status != new_status:
                if new_status == "completed" and old_status != "completed":
                    pipe.hincrby(mkey, "completed", 1)
                elif old_status == "completed" and new_status != "completed":
                    pipe.hincrby(mkey, "completed", -1)

            pipe.expire(dkey, _TTL_DAY)
            pipe.expire(mkey, _TTL_DAY)
            await pipe.execute()
            return task
        except Exception as exc:
            logger.warning("task_cache update_task error: %s", exc)
            return None

    async def delete_task(
        self,
        user_id: uuid.UUID,
        target_date: date,
        task_id: str,
        was_completed: bool,
    ) -> bool:
        """
        Remove a task from the hash and decrement meta counters.

        Returns ``False`` on Redis failure.
        """
        try:
            client = await get_redis()
            uid = str(user_id)
            dt = target_date.isoformat()
            dkey = _data_key(uid, dt)
            mkey = _meta_key(uid, dt)

            pipe = client.pipeline(transaction=False)
            pipe.hdel(dkey, task_id)
            pipe.hincrby(mkey, "total", -1)
            if was_completed:
                pipe.hincrby(mkey, "completed", -1)
            pipe.expire(dkey, _TTL_DAY)
            pipe.expire(mkey, _TTL_DAY)
            await pipe.execute()
            return True
        except Exception as exc:
            logger.warning("task_cache delete_task error: %s", exc)
            return False

    # ---- hydration (cold-start / cache miss) -----------------------------

    async def hydrate_from_db(
        self,
        user_id: uuid.UUID,
        target_date: date,
        tasks: list[dict],
    ) -> bool:
        """
        Populate the Redis hash from a list of task API dicts fetched from
        PostgreSQL.  Sets both the data hash and the meta hash.

        *tasks* should already be serialised via ``Task.to_api_dict()``.

        Returns ``False`` on Redis failure.
        """
        try:
            client = await get_redis()
            uid = str(user_id)
            dt = target_date.isoformat()
            dkey = _data_key(uid, dt)
            mkey = _meta_key(uid, dt)

            pipe = client.pipeline(transaction=False)
            # Clear stale data first
            pipe.delete(dkey)
            pipe.delete(mkey)

            if tasks:
                for t in tasks:
                    pipe.hset(dkey, t["id"], json.dumps(t, default=str))

            total = len(tasks)
            completed = sum(
                1 for t in tasks if t.get("status") == "completed"
            )
            pipe.hset(mkey, mapping={"total": total, "completed": completed})

            # Even empty days get a marker so we don't re-hydrate every time.
            # Use a sentinel field if there are no tasks.
            if not tasks:
                pipe.hset(dkey, "__empty__", "1")

            pipe.expire(dkey, _TTL_DAY)
            pipe.expire(mkey, _TTL_DAY)
            await pipe.execute()
            return True
        except Exception as exc:
            logger.warning("task_cache hydrate_from_db error: %s", exc)
            return False

    async def is_hydrated(
        self,
        user_id: uuid.UUID,
        target_date: date,
    ) -> Optional[bool]:
        """
        Check whether the data key exists (i.e. has been hydrated).

        Returns ``None`` on Redis failure.
        """
        try:
            client = await get_redis()
            key = _data_key(str(user_id), target_date.isoformat())
            return await client.exists(key) > 0
        except Exception as exc:
            logger.warning("task_cache is_hydrated error: %s", exc)
            return None

    # ---- sync queue ------------------------------------------------------

    async def enqueue_sync(
        self,
        op: str,
        data: dict,
    ) -> bool:
        """
        Append a mutation to the Redis Stream for background sync to
        PostgreSQL.

        *op* is one of: CREATE, BATCH_CREATE, UPDATE, BATCH_UPDATE,
        STATUS_UPDATE, DELETE.

        Returns ``False`` on Redis failure.
        """
        try:
            client = await get_redis()
            entry = {
                "op": op,
                "payload": json.dumps(data, default=str),
            }
            await client.xadd(
                _SYNC_STREAM,
                entry,
                maxlen=_SYNC_MAXLEN,
                approximate=True,
            )
            return True
        except Exception as exc:
            logger.warning("task_cache enqueue_sync error: %s", exc)
            return False
