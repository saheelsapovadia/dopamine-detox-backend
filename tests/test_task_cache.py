"""
Task Cache-First Architecture Tests
=====================================

Tests for the cache-first task API including:
- Cache reads (Redis Hash)
- Write-behind sync (enqueue to stream)
- Cache miss hydration from DB
- Redis failure graceful degradation
- High-priority conflict validation against cache
- Sync worker DB operations
"""

import json
import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.task_cache import TaskCacheService, _data_key, _meta_key


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_task_dict(
    *,
    task_id: str | None = None,
    user_id: str = "00000000-0000-0000-0000-000000000001",
    priority: str = "medium",
    status: str = "pending",
    title: str = "Test task",
    task_date: str = "2026-02-10",
) -> dict:
    """Build a minimal API-format task dict for testing."""
    return {
        "id": task_id or str(uuid.uuid4()),
        "userId": user_id,
        "title": title,
        "subtitle": None,
        "category": "WORK",
        "priority": priority,
        "durationMins": 25,
        "iconType": "default",
        "status": status,
        "date": task_date,
        "orderIndex": 0,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }


# A fixed user UUID used across tests
USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
TODAY = date(2026, 2, 10)


# ---------------------------------------------------------------------------
# TaskCacheService unit tests
# ---------------------------------------------------------------------------

class TestGetTasksForDate:
    """Tests for TaskCacheService.get_tasks_for_date"""

    @pytest.mark.asyncio
    async def test_returns_tasks_from_redis_hash(self):
        """When Redis has data, return parsed and sorted task list."""
        cache = TaskCacheService()
        t1 = _make_task_dict(priority="medium", title="Later task")
        t2 = _make_task_dict(priority="high", title="Priority task")

        mock_client = AsyncMock()
        mock_client.hgetall.return_value = {
            t1["id"]: json.dumps(t1),
            t2["id"]: json.dumps(t2),
        }

        with patch("app.services.task_cache.get_redis", return_value=mock_client):
            result = await cache.get_tasks_for_date(USER_ID, TODAY)

        assert result is not None
        assert len(result) == 2
        # High priority should sort first
        assert result[0]["priority"] == "high"
        assert result[1]["priority"] == "medium"

    @pytest.mark.asyncio
    async def test_returns_none_on_cache_miss(self):
        """When Redis key doesn't exist, return None (caller hydrates)."""
        cache = TaskCacheService()
        mock_client = AsyncMock()
        mock_client.hgetall.return_value = {}

        with patch("app.services.task_cache.get_redis", return_value=mock_client):
            result = await cache.get_tasks_for_date(USER_ID, TODAY)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_redis_error(self):
        """On Redis failure, return None for graceful degradation."""
        cache = TaskCacheService()
        mock_client = AsyncMock()
        mock_client.hgetall.side_effect = ConnectionError("Redis down")

        with patch("app.services.task_cache.get_redis", return_value=mock_client):
            result = await cache.get_tasks_for_date(USER_ID, TODAY)

        assert result is None


class TestGetHighPriorityTask:
    """Tests for high-priority conflict validation against cache."""

    @pytest.mark.asyncio
    async def test_finds_existing_high_priority(self):
        """Returns the high-priority task if one exists."""
        cache = TaskCacheService()
        t_high = _make_task_dict(priority="high", title="Priority")
        t_med = _make_task_dict(priority="medium", title="Normal")

        mock_client = AsyncMock()
        mock_client.hgetall.return_value = {
            t_high["id"]: json.dumps(t_high),
            t_med["id"]: json.dumps(t_med),
        }

        with patch("app.services.task_cache.get_redis", return_value=mock_client):
            result = await cache.get_high_priority_task(USER_ID, TODAY)

        assert result is not None
        assert result["priority"] == "high"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_high_priority(self):
        """Returns None when no high-priority task exists."""
        cache = TaskCacheService()
        t1 = _make_task_dict(priority="medium")
        t2 = _make_task_dict(priority="low")

        mock_client = AsyncMock()
        mock_client.hgetall.return_value = {
            t1["id"]: json.dumps(t1),
            t2["id"]: json.dumps(t2),
        }

        with patch("app.services.task_cache.get_redis", return_value=mock_client):
            result = await cache.get_high_priority_task(USER_ID, TODAY)

        assert result is None


class TestSetTask:
    """Tests for cache write operations."""

    @pytest.mark.asyncio
    async def test_set_task_writes_hash_and_meta(self):
        """set_task should HSET the task and bump meta.total."""
        cache = TaskCacheService()
        task = _make_task_dict()

        mock_pipe = AsyncMock()
        mock_pipe.execute.return_value = [True, True, True, True]
        mock_client = AsyncMock()
        mock_client.pipeline.return_value = mock_pipe

        with patch("app.services.task_cache.get_redis", return_value=mock_client):
            ok = await cache.set_task(USER_ID, TODAY, task["id"], task)

        assert ok is True
        # Verify pipeline was used
        mock_client.pipeline.assert_called_once()
        # HSET, HINCRBY total, EXPIRE data, EXPIRE meta = 4 calls minimum
        assert mock_pipe.hset.call_count >= 1
        assert mock_pipe.hincrby.call_count >= 1

    @pytest.mark.asyncio
    async def test_set_task_returns_false_on_redis_error(self):
        """On Redis failure, set_task returns False."""
        cache = TaskCacheService()
        task = _make_task_dict()

        mock_client = AsyncMock()
        mock_client.pipeline.side_effect = ConnectionError("Redis down")

        with patch("app.services.task_cache.get_redis", return_value=mock_client):
            ok = await cache.set_task(USER_ID, TODAY, task["id"], task)

        assert ok is False


class TestUpdateTask:
    """Tests for cache update operations."""

    @pytest.mark.asyncio
    async def test_merges_updates_into_cached_task(self):
        """update_task should merge fields and write back."""
        cache = TaskCacheService()
        original = _make_task_dict(title="Old title", status="pending")

        mock_pipe = AsyncMock()
        mock_pipe.execute.return_value = [True, True, True]
        mock_client = AsyncMock()
        mock_client.hget.return_value = json.dumps(original)
        mock_client.pipeline.return_value = mock_pipe

        with patch("app.services.task_cache.get_redis", return_value=mock_client):
            result = await cache.update_task(
                USER_ID, TODAY, original["id"], {"title": "New title"},
            )

        assert result is not None
        assert result["title"] == "New title"
        assert result["status"] == "pending"  # unchanged

    @pytest.mark.asyncio
    async def test_adjusts_completed_counter_on_status_change(self):
        """When status changes to completed, meta.completed should increment."""
        cache = TaskCacheService()
        original = _make_task_dict(status="pending")

        mock_pipe = AsyncMock()
        mock_pipe.execute.return_value = [True, True, True, True]
        mock_client = AsyncMock()
        mock_client.hget.return_value = json.dumps(original)
        mock_client.pipeline.return_value = mock_pipe

        with patch("app.services.task_cache.get_redis", return_value=mock_client):
            result = await cache.update_task(
                USER_ID, TODAY, original["id"], {"status": "completed"},
            )

        assert result is not None
        assert result["status"] == "completed"
        # Verify HINCRBY was called for completed counter
        hincrby_calls = [
            call for call in mock_pipe.hincrby.call_args_list
            if "completed" in str(call)
        ]
        assert len(hincrby_calls) >= 1

    @pytest.mark.asyncio
    async def test_returns_none_when_task_not_in_cache(self):
        """Returns None when the task ID is not found in the hash."""
        cache = TaskCacheService()
        mock_client = AsyncMock()
        mock_client.hget.return_value = None

        with patch("app.services.task_cache.get_redis", return_value=mock_client):
            result = await cache.update_task(
                USER_ID, TODAY, "nonexistent", {"title": "x"},
            )

        assert result is None


class TestDeleteTask:
    """Tests for cache delete operations."""

    @pytest.mark.asyncio
    async def test_removes_from_hash_and_decrements_meta(self):
        """delete_task should HDEL and decrement meta counters."""
        cache = TaskCacheService()

        mock_pipe = AsyncMock()
        mock_pipe.execute.return_value = [1, True, True, True]
        mock_client = AsyncMock()
        mock_client.pipeline.return_value = mock_pipe

        with patch("app.services.task_cache.get_redis", return_value=mock_client):
            ok = await cache.delete_task(
                USER_ID, TODAY, "some-id", was_completed=False,
            )

        assert ok is True
        mock_pipe.hdel.assert_called_once()
        # total should be decremented
        mock_pipe.hincrby.assert_any_call(
            _meta_key(str(USER_ID), TODAY.isoformat()), "total", -1,
        )


class TestGetDaySummaries:
    """Tests for day summary pipeline reads."""

    @pytest.mark.asyncio
    async def test_builds_summaries_from_meta_hashes(self):
        """get_day_summaries should pipeline 7 HGETALL calls."""
        cache = TaskCacheService()

        # Mock pipeline returning 7 meta hashes
        results = []
        for i in range(7):
            results.append({"total": "3", "completed": str(i % 4)})

        mock_pipe = AsyncMock()
        mock_pipe.execute.return_value = results
        mock_client = AsyncMock()
        mock_client.pipeline.return_value = mock_pipe

        with patch("app.services.task_cache.get_redis", return_value=mock_client):
            summaries = await cache.get_day_summaries(USER_ID, TODAY)

        assert summaries is not None
        assert len(summaries) == 7
        # First should be today
        assert summaries[0]["date"] == TODAY.isoformat()
        assert summaries[0]["totalTasks"] == 3
        assert "label" in summaries[0]

    @pytest.mark.asyncio
    async def test_returns_none_on_redis_error(self):
        """On Redis failure, returns None."""
        cache = TaskCacheService()
        mock_client = AsyncMock()
        mock_client.pipeline.side_effect = ConnectionError("Redis down")

        with patch("app.services.task_cache.get_redis", return_value=mock_client):
            result = await cache.get_day_summaries(USER_ID, TODAY)

        assert result is None


class TestHydration:
    """Tests for cache hydration from DB."""

    @pytest.mark.asyncio
    async def test_hydrate_populates_hash_and_meta(self):
        """hydrate_from_db should write tasks to hash and set counters."""
        cache = TaskCacheService()
        tasks = [
            _make_task_dict(status="completed"),
            _make_task_dict(status="pending"),
            _make_task_dict(status="pending"),
        ]

        mock_pipe = AsyncMock()
        mock_pipe.execute.return_value = [True] * 10
        mock_client = AsyncMock()
        mock_client.pipeline.return_value = mock_pipe

        with patch("app.services.task_cache.get_redis", return_value=mock_client):
            ok = await cache.hydrate_from_db(USER_ID, TODAY, tasks)

        assert ok is True
        # Should have 3 HSET calls (one per task)
        assert mock_pipe.hset.call_count >= 3

    @pytest.mark.asyncio
    async def test_hydrate_empty_date_sets_sentinel(self):
        """Hydrating with no tasks should set a sentinel so we don't re-hydrate."""
        cache = TaskCacheService()

        mock_pipe = AsyncMock()
        mock_pipe.execute.return_value = [True] * 5
        mock_client = AsyncMock()
        mock_client.pipeline.return_value = mock_pipe

        with patch("app.services.task_cache.get_redis", return_value=mock_client):
            ok = await cache.hydrate_from_db(USER_ID, TODAY, [])

        assert ok is True
        # Should have set the __empty__ sentinel
        sentinel_calls = [
            call for call in mock_pipe.hset.call_args_list
            if "__empty__" in str(call)
        ]
        assert len(sentinel_calls) >= 1


class TestEnqueueSync:
    """Tests for the sync queue."""

    @pytest.mark.asyncio
    async def test_enqueues_to_redis_stream(self):
        """enqueue_sync should XADD to the sync stream."""
        cache = TaskCacheService()
        task = _make_task_dict()

        mock_client = AsyncMock()
        mock_client.xadd.return_value = "1234567890-0"

        with patch("app.services.task_cache.get_redis", return_value=mock_client):
            ok = await cache.enqueue_sync("CREATE", task)

        assert ok is True
        mock_client.xadd.assert_called_once()
        call_args = mock_client.xadd.call_args
        assert call_args[0][0] == "stream:tasks:sync"
        entry = call_args[0][1]
        assert entry["op"] == "CREATE"
        assert "payload" in entry

    @pytest.mark.asyncio
    async def test_returns_false_on_redis_error(self):
        """On Redis failure, enqueue returns False."""
        cache = TaskCacheService()

        mock_client = AsyncMock()
        mock_client.xadd.side_effect = ConnectionError("Redis down")

        with patch("app.services.task_cache.get_redis", return_value=mock_client):
            ok = await cache.enqueue_sync("CREATE", {"id": "x"})

        assert ok is False


# ---------------------------------------------------------------------------
# Sync worker unit tests
# ---------------------------------------------------------------------------

class TestSyncWorkerOperations:
    """Tests for sync worker DB write operations."""

    @pytest.mark.asyncio
    async def test_sync_create_inserts_task(self):
        """_sync_create should execute an INSERT statement."""
        from app.services.sync_worker import TaskSyncWorker

        worker = TaskSyncWorker()
        task = _make_task_dict()

        mock_session = AsyncMock()
        mock_session.execute.return_value = MagicMock()

        await worker._sync_create(mock_session, task)
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_delete_executes_delete(self):
        """_sync_delete should execute a DELETE statement."""
        from app.services.sync_worker import TaskSyncWorker

        worker = TaskSyncWorker()
        tid = str(uuid.uuid4())

        mock_session = AsyncMock()
        mock_session.execute.return_value = MagicMock()

        await worker._sync_delete(mock_session, {"id": tid})
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_status_update(self):
        """_sync_status_update should execute an UPDATE for status."""
        from app.services.sync_worker import TaskSyncWorker

        worker = TaskSyncWorker()
        tid = str(uuid.uuid4())

        mock_session = AsyncMock()
        mock_session.execute.return_value = MagicMock()

        await worker._sync_status_update(mock_session, {
            "id": tid,
            "status": "completed",
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        })
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_batch_create_calls_create_per_task(self):
        """_sync_batch_create should INSERT each task."""
        from app.services.sync_worker import TaskSyncWorker

        worker = TaskSyncWorker()
        tasks = [_make_task_dict(), _make_task_dict()]

        mock_session = AsyncMock()
        mock_session.execute.return_value = MagicMock()

        await worker._sync_batch_create(mock_session, {"tasks": tasks})
        assert mock_session.execute.call_count == 2
