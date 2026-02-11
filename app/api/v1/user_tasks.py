"""
User Tasks API Endpoints (v2) — Cache-First
=============================================

Handles the HomeScreen-facing task endpoints with user-scoped paths.

**Architecture**: reads and writes hit Redis first; mutations are
asynchronously synced to PostgreSQL via a background worker.  If Redis
is unavailable the endpoints fall back to direct DB access transparently.

The DB session is **lazy** — it is only opened when actually needed
(fallback / hydration).  On a pure cache-hit path, zero DB overhead.

Route prefix: /api/v1/users/{user_id}/tasks

Endpoints:
    GET    /{user_id}/tasks/daily?date=  — Fetch daily tasks (priority + later) + day summaries
    POST   /{user_id}/tasks              — Create a single task
    POST   /{user_id}/tasks/batch        — Batch-create tasks ("Plan My Day")
    PUT    /{user_id}/tasks/batch        — Batch-update tasks ("Edit Tasks")
    PATCH  /{user_id}/tasks/{task_id}    — Update single task status
    DELETE /{user_id}/tasks/{task_id}    — Delete a task
"""

import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.db.session import LazyDB, get_lazy_db
from app.dependencies import CurrentUser
from app.schemas.task import (
    BatchCreateTasksRequest,
    BatchUpdateTasksRequest,
    CreateTaskRequest,
    UpdateTaskStatusRequest,
)
from app.models.task import TaskPriority
from app.services.task_cache import TaskCacheService
from app.services.task_service import (
    HighPriorityConflictError,
    TaskNotFoundError,
    TaskService,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Shared cache service instance (stateless, safe to reuse)
_cache = TaskCacheService()


# =============================================================================
# Helpers
# =============================================================================

def _verify_user_ownership(current_user, path_user_id: uuid.UUID) -> None:
    """
    Ensure the authenticated user matches the {user_id} in the path.

    Raises 403 if mismatched.
    """
    if current_user.user_id != path_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "FORBIDDEN",
                "message": "Cannot access another user's tasks",
            },
        )


def _task_to_api(task) -> dict:
    """Convert a Task model instance to the camelCase API dict."""
    return task.to_api_dict()


def _build_task_dict(
    *,
    user_id: uuid.UUID,
    title: str,
    category: str,
    priority: str,
    duration_mins: int,
    task_date: date,
    subtitle: Optional[str] = None,
    icon_type: str = "default",
    status_val: str = "pending",
    order_index: int = 0,
    task_id: Optional[str] = None,
) -> dict:
    """
    Build a plain-dict task in the API response format.

    UUID and timestamps are generated in Python so we can write to Redis
    without waiting for PostgreSQL.
    """
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": task_id or str(uuid.uuid4()),
        "userId": str(user_id),
        "title": title,
        "subtitle": subtitle,
        "category": category,
        "priority": priority,
        "durationMins": duration_mins,
        "iconType": icon_type,
        "status": status_val,
        "date": task_date.isoformat(),
        "orderIndex": order_index,
        "createdAt": now,
        "updatedAt": now,
    }


# =============================================================================
# Fallback helpers (used when Redis is unavailable)
# =============================================================================

async def _get_daily_from_db(
    lazy_db: LazyDB,
    user_id: uuid.UUID,
    query_date: date,
) -> dict:
    """Full DB-backed daily tasks response (fallback)."""
    db = await lazy_db.get()
    task_service = TaskService(db)
    result = await task_service.get_daily_tasks(user_id, query_date)
    response_data = {
        "date": result["date"],
        "hasTasks": result["hasTasks"],
        "priorityTask": (
            _task_to_api(result["priorityTask"])
            if result["priorityTask"]
            else None
        ),
        "laterTasks": [_task_to_api(t) for t in result["laterTasks"]],
        "daySummaries": result["daySummaries"],
    }
    return {"success": True, "data": response_data}


async def _hydrate_and_get(
    lazy_db: LazyDB,
    user_id: uuid.UUID,
    query_date: date,
) -> tuple[list[dict], list[dict] | None]:
    """
    Hydrate Redis from PostgreSQL on cache miss and return
    ``(tasks, summaries)``.

    If hydration fails we still return the DB data so the request succeeds.
    """
    db = await lazy_db.get()
    task_service = TaskService(db)
    db_tasks = await task_service.get_tasks_for_date(user_id, query_date)
    task_dicts = [_task_to_api(t) for t in db_tasks]

    # Hydrate cache (best-effort)
    await _cache.hydrate_from_db(user_id, query_date, task_dicts)

    # Also hydrate the surrounding 7 days for summaries
    summaries = await _cache.get_day_summaries(user_id, query_date)
    if summaries is None:
        # Summaries cache also failed; build from DB
        result = await task_service.get_daily_tasks(user_id, query_date)
        summaries = result["daySummaries"]

    return task_dicts, summaries


# =============================================================================
# GET /users/{user_id}/tasks/daily
# =============================================================================

@router.get(
    "/{user_id}/tasks/daily",
    summary="Fetch daily tasks",
    description="Fetches priority task, later tasks, and day summaries for the HomeScreen.",
)
async def get_daily_tasks(
    user_id: Annotated[uuid.UUID, Path(description="The authenticated user's ID")],
    current_user: CurrentUser,
    lazy_db: Annotated[LazyDB, Depends(get_lazy_db)],
    target_date: str | None = Query(
        default=None,
        alias="date",
        description="ISO date (YYYY-MM-DD). Defaults to today.",
    ),
):
    """
    GET /api/v1/users/{user_id}/tasks/daily?date=2026-02-07

    Cache-first: reads from Redis Hash.  On cache miss, hydrates from DB.
    Falls back to DB entirely if Redis is unavailable.
    DB session is only opened if needed (lazy).
    """
    t0 = time.perf_counter()
    _verify_user_ownership(current_user, user_id)

    # Parse date
    if target_date:
        try:
            query_date = date.fromisoformat(target_date)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "VALIDATION_ERROR",
                    "message": "Invalid date format. Use YYYY-MM-DD.",
                },
            )
    else:
        query_date = date.today()

    # --- Cache-first read ---
    cache_path = "cache_hit"
    tasks = await _cache.get_tasks_for_date(user_id, query_date)

    if tasks is None:
        # Cache miss or Redis down — hydrate from DB
        hydrated = await _cache.is_hydrated(user_id, query_date)
        if hydrated is None:
            # Redis is completely unavailable — full DB fallback
            cache_path = "db_fallback"
            logger.info(
                "daily_tasks path=db_fallback user=%s date=%s reason=redis_unavailable",
                user_id, query_date,
            )
            return await _get_daily_from_db(lazy_db, user_id, query_date)

        cache_path = "hydration"
        tasks_list, summaries = await _hydrate_and_get(lazy_db, user_id, query_date)
        tasks = tasks_list
    else:
        summaries = await _cache.get_day_summaries(user_id, query_date)
        if summaries is None:
            # Summaries failed but tasks succeeded — build summaries from DB
            cache_path = "cache_hit_partial"
            db = await lazy_db.get()
            task_service = TaskService(db)
            result = await task_service.get_daily_tasks(user_id, query_date)
            summaries = result["daySummaries"]

    # Build response
    has_tasks = len(tasks) > 0
    priority_task: Optional[dict] = None
    later_tasks: list[dict] = []

    for t in tasks:
        if t.get("priority") == "high" and priority_task is None:
            priority_task = t
        else:
            later_tasks.append(t)

    elapsed_ms = (time.perf_counter() - t0) * 1000
    logger.info(
        "daily_tasks path=%s user=%s date=%s tasks=%d elapsed=%.1fms",
        cache_path, user_id, query_date, len(tasks), elapsed_ms,
    )

    response_data = {
        "date": query_date.isoformat(),
        "hasTasks": has_tasks,
        "priorityTask": priority_task,
        "laterTasks": later_tasks,
        "daySummaries": summaries or [],
    }

    return {"success": True, "data": response_data}


# =============================================================================
# POST /users/{user_id}/tasks
# =============================================================================

@router.post(
    "/{user_id}/tasks",
    status_code=status.HTTP_201_CREATED,
    summary="Create a task",
    description="Creates a single task for the given date.",
)
async def create_user_task(
    user_id: Annotated[uuid.UUID, Path(description="The authenticated user's ID")],
    body: CreateTaskRequest,
    current_user: CurrentUser,
    lazy_db: Annotated[LazyDB, Depends(get_lazy_db)],
):
    """
    POST /api/v1/users/{user_id}/tasks

    Cache-first: writes to Redis, enqueues async DB sync, returns immediately.
    Falls back to direct DB write if Redis is unavailable.
    DB session is only opened if needed (lazy).
    """
    _verify_user_ownership(current_user, user_id)

    task_date = (
        date.fromisoformat(body.date) if body.date else date.today()
    )

    # --- Validate high-priority conflict against cache ---
    if body.priority == TaskPriority.HIGH:
        # Ensure cache is hydrated so we can check
        hydrated = await _cache.is_hydrated(user_id, task_date)
        if hydrated is False:
            # Hydrate first
            db = await lazy_db.get()
            task_service = TaskService(db)
            db_tasks = await task_service.get_tasks_for_date(user_id, task_date)
            await _cache.hydrate_from_db(
                user_id, task_date, [_task_to_api(t) for t in db_tasks],
            )
        if hydrated is None:
            # Redis unavailable — fall back to DB for the whole operation
            return await _create_task_db_fallback(lazy_db, current_user, user_id, body, task_date)

        existing_high = await _cache.get_high_priority_task(user_id, task_date)
        if existing_high is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "CONFLICT",
                    "message": "A high-priority task already exists for this date",
                },
            )

    # --- Build task dict ---
    task_dict = _build_task_dict(
        user_id=current_user.user_id,
        title=body.title,
        subtitle=body.subtitle,
        category=body.category.value,
        priority=body.priority.value,
        duration_mins=body.duration_mins,
        icon_type=body.icon_type.value,
        task_date=task_date,
    )

    # --- Write to cache ---
    ok = await _cache.set_task(user_id, task_date, task_dict["id"], task_dict)
    if not ok:
        # Redis write failed — fall back to DB
        return await _create_task_db_fallback(lazy_db, current_user, user_id, body, task_date)

    # --- Enqueue async DB sync ---
    await _cache.enqueue_sync("CREATE", task_dict)

    return {
        "success": True,
        "data": task_dict,
    }


async def _create_task_db_fallback(
    lazy_db: LazyDB,
    current_user,
    user_id: uuid.UUID,
    body: CreateTaskRequest,
    task_date: date,
) -> dict:
    """Synchronous DB-only create (fallback)."""
    db = await lazy_db.get()
    task_service = TaskService(db)
    try:
        task = await task_service.create_task_v2(
            user_id=current_user.user_id, task_data=body,
        )
    except HighPriorityConflictError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "CONFLICT",
                "message": "A high-priority task already exists for this date",
            },
        )
    return {"success": True, "data": _task_to_api(task)}


# =============================================================================
# POST /users/{user_id}/tasks/batch
# =============================================================================

@router.post(
    "/{user_id}/tasks/batch",
    status_code=status.HTTP_201_CREATED,
    summary="Batch-create tasks",
    description="Creates multiple tasks at once (Plan My Day flow).",
)
async def batch_create_user_tasks(
    user_id: Annotated[uuid.UUID, Path(description="The authenticated user's ID")],
    body: BatchCreateTasksRequest,
    current_user: CurrentUser,
    lazy_db: Annotated[LazyDB, Depends(get_lazy_db)],
):
    """
    POST /api/v1/users/{user_id}/tasks/batch

    Cache-first: writes batch to Redis, enqueues async DB sync.
    Falls back to direct DB write if Redis is unavailable.
    DB session is only opened if needed (lazy).
    """
    _verify_user_ownership(current_user, user_id)

    task_date = (
        date.fromisoformat(body.date) if body.date else date.today()
    )

    # --- Validate high-priority count ---
    high_count = sum(1 for t in body.tasks if t.priority == TaskPriority.HIGH)
    if high_count > 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "Only one high-priority task is allowed per date",
            },
        )

    if high_count == 1:
        # Ensure cache hydrated
        hydrated = await _cache.is_hydrated(user_id, task_date)
        if hydrated is False:
            db = await lazy_db.get()
            task_service = TaskService(db)
            db_tasks = await task_service.get_tasks_for_date(user_id, task_date)
            await _cache.hydrate_from_db(
                user_id, task_date, [_task_to_api(t) for t in db_tasks],
            )
        if hydrated is None:
            return await _batch_create_db_fallback(
                lazy_db, current_user, user_id, body, task_date,
            )
        existing_high = await _cache.get_high_priority_task(user_id, task_date)
        if existing_high is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "CONFLICT",
                    "message": "A high-priority task already exists for this date",
                },
            )

    # --- Build task dicts ---
    task_dicts: list[dict] = []
    for i, item in enumerate(body.tasks):
        task_dicts.append(
            _build_task_dict(
                user_id=current_user.user_id,
                title=item.title,
                subtitle=item.subtitle,
                category=item.category.value,
                priority=item.priority.value,
                duration_mins=item.duration_mins,
                icon_type=item.icon_type.value,
                task_date=task_date,
                order_index=i,
            )
        )

    # --- Write batch to cache ---
    ok = await _cache.set_tasks_batch(user_id, task_date, task_dicts)
    if not ok:
        return await _batch_create_db_fallback(
            lazy_db, current_user, user_id, body, task_date,
        )

    # --- Enqueue async DB sync ---
    await _cache.enqueue_sync("BATCH_CREATE", {
        "tasks": task_dicts,
    })

    return {
        "success": True,
        "data": {
            "date": task_date.isoformat(),
            "created": len(task_dicts),
            "tasks": task_dicts,
        },
    }


async def _batch_create_db_fallback(
    lazy_db: LazyDB,
    current_user,
    user_id: uuid.UUID,
    body: BatchCreateTasksRequest,
    task_date: date,
) -> dict:
    """Synchronous DB-only batch create (fallback)."""
    db = await lazy_db.get()
    task_service = TaskService(db)
    try:
        created_tasks = await task_service.batch_create_tasks(
            user_id=current_user.user_id,
            task_items=body.tasks,
            task_date=task_date,
        )
    except HighPriorityConflictError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "CONFLICT",
                "message": "A high-priority task already exists for this date",
            },
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "VALIDATION_ERROR", "message": str(exc)},
        )
    return {
        "success": True,
        "data": {
            "date": task_date.isoformat(),
            "created": len(created_tasks),
            "tasks": [_task_to_api(t) for t in created_tasks],
        },
    }


# =============================================================================
# PUT /users/{user_id}/tasks/batch
# =============================================================================

@router.put(
    "/{user_id}/tasks/batch",
    summary="Batch-update tasks",
    description="Updates multiple tasks at once (Edit Tasks flow). Partial update semantics.",
)
async def batch_update_user_tasks(
    user_id: Annotated[uuid.UUID, Path(description="The authenticated user's ID")],
    body: BatchUpdateTasksRequest,
    current_user: CurrentUser,
    lazy_db: Annotated[LazyDB, Depends(get_lazy_db)],
):
    """
    PUT /api/v1/users/{user_id}/tasks/batch

    Cache-first: reads existing tasks from Redis, applies partial updates,
    writes back, enqueues DB sync.

    If a task's priority is changed to "high", any existing high-priority task
    for the same date is automatically demoted to "medium".
    DB session is only opened if needed (lazy).
    """
    _verify_user_ownership(current_user, user_id)

    try:
        task_date = date.fromisoformat(body.date)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "Invalid date format. Use YYYY-MM-DD.",
            },
        )

    # --- Pre-validate: at most one high-priority in the request ---
    high_count = sum(
        1 for t in body.tasks if t.priority == TaskPriority.HIGH
    )
    if high_count > 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "CONFLICT",
                "message": "Only one task can have high priority per date",
            },
        )

    # --- Ensure cache is hydrated ---
    hydrated = await _cache.is_hydrated(user_id, task_date)
    if hydrated is None:
        # Redis unavailable — full DB fallback
        return await _batch_update_db_fallback(
            lazy_db, current_user, user_id, body, task_date,
        )
    if hydrated is False:
        db = await lazy_db.get()
        task_service = TaskService(db)
        db_tasks = await task_service.get_tasks_for_date(user_id, task_date)
        await _cache.hydrate_from_db(
            user_id, task_date, [_task_to_api(t) for t in db_tasks],
        )

    # --- Identify new high-priority and demote existing if needed ---
    new_high_id: Optional[str] = None
    for item in body.tasks:
        if item.priority == TaskPriority.HIGH:
            new_high_id = item.id
            break

    if new_high_id is not None:
        existing_high = await _cache.get_high_priority_task(user_id, task_date)
        if existing_high and existing_high["id"] != new_high_id:
            # Demote the old high-priority task to medium
            await _cache.update_task(
                user_id, task_date, existing_high["id"],
                {"priority": "medium"},
            )
            # Also enqueue the demotion for DB sync
            await _cache.enqueue_sync("UPDATE", {
                "id": existing_high["id"],
                "updates": {"priority": "medium"},
            })

    # --- Apply partial updates in cache ---
    updated_summaries: list[dict] = []
    sync_tasks: list[dict] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    for item in body.tasks:
        updates: dict = {}
        if item.title is not None:
            updates["title"] = item.title
        if item.subtitle is not None:
            updates["subtitle"] = item.subtitle
        if item.category is not None:
            updates["category"] = item.category.value
        if item.priority is not None:
            updates["priority"] = item.priority.value
        if item.duration_mins is not None:
            updates["durationMins"] = item.duration_mins
        if item.icon_type is not None:
            updates["iconType"] = item.icon_type.value

        if not updates:
            # Nothing to update for this item, but still include in response
            cached_task = await _cache.get_task(user_id, task_date, item.id)
            if cached_task is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "code": "VALIDATION_ERROR",
                        "message": f"Task {item.id} not found for date {task_date.isoformat()}",
                    },
                )
            updated_summaries.append({
                "id": cached_task["id"],
                "title": cached_task.get("title", ""),
                "priority": cached_task.get("priority", "medium"),
                "status": cached_task.get("status", "pending"),
                "updatedAt": cached_task.get("updatedAt"),
            })
            continue

        updated_task = await _cache.update_task(
            user_id, task_date, item.id, updates,
        )
        if updated_task is None:
            # Task not found in cache — could be Redis error or missing task
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "VALIDATION_ERROR",
                    "message": f"Task {item.id} not found for date {task_date.isoformat()}",
                },
            )

        updated_summaries.append({
            "id": updated_task["id"],
            "title": updated_task.get("title", ""),
            "priority": updated_task.get("priority", "medium"),
            "status": updated_task.get("status", "pending"),
            "updatedAt": updated_task.get("updatedAt", now_iso),
        })

        sync_tasks.append({
            "id": item.id,
            "updates": updates,
            "updatedAt": now_iso,
        })

    # --- Enqueue async DB sync ---
    if sync_tasks:
        await _cache.enqueue_sync("BATCH_UPDATE", {"tasks": sync_tasks})

    return {
        "success": True,
        "data": {
            "date": task_date.isoformat(),
            "updated": len(updated_summaries),
            "tasks": updated_summaries,
        },
    }


async def _batch_update_db_fallback(
    lazy_db: LazyDB,
    current_user,
    user_id: uuid.UUID,
    body: BatchUpdateTasksRequest,
    task_date: date,
) -> dict:
    """Synchronous DB-only batch update (fallback)."""
    db = await lazy_db.get()
    task_service = TaskService(db)
    try:
        updated_tasks = await task_service.batch_update_tasks(
            user_id=current_user.user_id,
            task_items=body.tasks,
            task_date=task_date,
        )
    except TaskNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "VALIDATION_ERROR",
                "message": f"Task {exc.task_id} not found for date {exc.task_date.isoformat()}",
            },
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CONFLICT", "message": str(exc)},
        )
    return {
        "success": True,
        "data": {
            "date": task_date.isoformat(),
            "updated": len(updated_tasks),
            "tasks": [
                {
                    "id": str(t.task_id),
                    "title": t.title,
                    "priority": t.priority.value,
                    "status": t.status.value,
                    "updatedAt": t.updated_at.isoformat() if t.updated_at else None,
                }
                for t in updated_tasks
            ],
        },
    }


# =============================================================================
# PATCH /users/{user_id}/tasks/{task_id}
# =============================================================================

@router.patch(
    "/{user_id}/tasks/{task_id}",
    summary="Update single task status",
    description="Updates a single task's status (e.g. pending -> in_progress -> completed).",
)
async def update_user_task_status(
    user_id: Annotated[uuid.UUID, Path(description="The authenticated user's ID")],
    task_id: Annotated[uuid.UUID, Path(description="The task to update")],
    body: UpdateTaskStatusRequest,
    current_user: CurrentUser,
    lazy_db: Annotated[LazyDB, Depends(get_lazy_db)],
):
    """
    PATCH /api/v1/users/{user_id}/tasks/{task_id}

    Cache-first: updates status in Redis, enqueues async DB sync.
    Falls back to DB if Redis is unavailable.
    DB session is only opened if needed (lazy).
    """
    _verify_user_ownership(current_user, user_id)

    tid = str(task_id)

    # We need the task's date to locate it in the cache.
    # Try a quick scan of recent dates (today and surrounding days).
    task_dict: Optional[dict] = None
    task_date_str: Optional[str] = None

    # Try today first, then +/- a few days
    today = date.today()
    candidate_dates = [today] + [
        today + timedelta(days=d) for d in [-1, 1, -2, 2, -3, 3]
    ]

    for d in candidate_dates:
        cached = await _cache.get_task(user_id, d, tid)
        if cached is not None:
            task_dict = cached
            task_date_str = d.isoformat()
            break

    if task_dict is None:
        # Not found in cache — try DB lookup and hydrate
        db = await lazy_db.get()
        task_service = TaskService(db)
        db_task = await task_service.get_task_by_id(task_id, current_user.user_id)
        if db_task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "NOT_FOUND", "message": "Task not found"},
            )
        task_dict = _task_to_api(db_task)
        task_date_str = db_task.due_date.isoformat() if db_task.due_date else today.isoformat()
        # Hydrate this date's tasks into cache for future requests
        db_tasks = await task_service.get_tasks_for_date(
            current_user.user_id,
            db_task.due_date or today,
        )
        await _cache.hydrate_from_db(
            user_id, db_task.due_date or today,
            [_task_to_api(t) for t in db_tasks],
        )

    target_date = date.fromisoformat(task_date_str)

    # --- Update status in cache ---
    now_iso = datetime.now(timezone.utc).isoformat()
    updated = await _cache.update_task(
        user_id, target_date, tid,
        {"status": body.status.value, "updatedAt": now_iso},
    )

    if updated is None:
        # Cache update failed — DB fallback
        db = await lazy_db.get()
        task_service = TaskService(db)
        db_task = await task_service.get_task_by_id(task_id, current_user.user_id)
        if db_task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "NOT_FOUND", "message": "Task not found"},
            )
        db_task.status = body.status
        await db.flush()
        return {"success": True, "data": _task_to_api(db_task)}

    # --- Enqueue async DB sync ---
    await _cache.enqueue_sync("STATUS_UPDATE", {
        "id": tid,
        "status": body.status.value,
        "updatedAt": now_iso,
    })

    return {"success": True, "data": updated}


# =============================================================================
# DELETE /users/{user_id}/tasks/{task_id}
# =============================================================================

@router.delete(
    "/{user_id}/tasks/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a task",
    description="Permanently deletes a task.",
)
async def delete_user_task(
    user_id: Annotated[uuid.UUID, Path(description="The authenticated user's ID")],
    task_id: Annotated[uuid.UUID, Path(description="The task to delete")],
    current_user: CurrentUser,
    lazy_db: Annotated[LazyDB, Depends(get_lazy_db)],
):
    """
    DELETE /api/v1/users/{user_id}/tasks/{task_id}

    Cache-first: removes from Redis, enqueues async DB deletion.
    Falls back to DB if Redis is unavailable.
    DB session is only opened if needed (lazy).
    """
    _verify_user_ownership(current_user, user_id)

    tid = str(task_id)

    # Locate the task in cache (need date + completion status)
    task_dict: Optional[dict] = None
    task_date_obj: Optional[date] = None

    today = date.today()
    candidate_dates = [today] + [
        today + timedelta(days=d) for d in [-1, 1, -2, 2, -3, 3]
    ]

    for d in candidate_dates:
        cached = await _cache.get_task(user_id, d, tid)
        if cached is not None:
            task_dict = cached
            task_date_obj = d
            break

    if task_dict is None:
        # Not in cache — look up in DB
        db = await lazy_db.get()
        task_service = TaskService(db)
        db_task = await task_service.get_task_by_id(task_id, current_user.user_id)
        if db_task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "NOT_FOUND", "message": "Task not found"},
            )
        task_dict = _task_to_api(db_task)
        task_date_obj = db_task.due_date or today

    was_completed = task_dict.get("status") == "completed"

    # --- Remove from cache ---
    ok = await _cache.delete_task(user_id, task_date_obj, tid, was_completed)
    if not ok:
        # Cache delete failed — DB fallback
        db = await lazy_db.get()
        task_service = TaskService(db)
        db_task = await task_service.get_task_by_id(task_id, current_user.user_id)
        if db_task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "NOT_FOUND", "message": "Task not found"},
            )
        await task_service.delete_task(db_task)
        return  # 204

    # --- Enqueue async DB sync ---
    await _cache.enqueue_sync("DELETE", {"id": tid})

    # 204 No Content — return nothing
