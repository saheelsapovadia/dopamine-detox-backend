"""
User Tasks API Endpoints (v2)
==============================

Handles the HomeScreen-facing task endpoints with user-scoped paths.

Route prefix: /api/v1/users/{user_id}/tasks

Endpoints:
    GET    /{user_id}/tasks/daily?date=  — Fetch daily tasks (priority + later) + day summaries
    POST   /{user_id}/tasks              — Create a single task
    POST   /{user_id}/tasks/batch        — Batch-create tasks ("Plan My Day")
    PUT    /{user_id}/tasks/batch        — Batch-update tasks ("Edit Tasks")
    PATCH  /{user_id}/tasks/{task_id}    — Update single task status
    DELETE /{user_id}/tasks/{task_id}    — Delete a task
"""

from datetime import date
from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import CurrentUser
from app.schemas.task import (
    BatchCreateTasksRequest,
    BatchUpdateTasksRequest,
    CreateTaskRequest,
    UpdateTaskStatusRequest,
)
from app.services.cache import CacheKeys, CacheManager
from app.services.task_service import (
    HighPriorityConflictError,
    TaskNotFoundError,
    TaskService,
)

router = APIRouter()


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
    db: Annotated[AsyncSession, Depends(get_db)],
    target_date: str | None = Query(
        default=None,
        alias="date",
        description="ISO date (YYYY-MM-DD). Defaults to today.",
    ),
):
    """
    GET /api/v1/users/{user_id}/tasks/daily?date=2026-02-07

    Returns structured data for the HomeScreen:
    - hasTasks toggle
    - priorityTask (high priority)
    - laterTasks (medium / low)
    - daySummaries (day-selector pills)
    """
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

    # Try cache
    cache_key = CacheKeys.daily_tasks(str(user_id), query_date.isoformat())
    cached = await CacheManager.get(cache_key)
    if cached:
        return {"success": True, "data": cached}

    # Fetch from service
    task_service = TaskService(db)
    result = await task_service.get_daily_tasks(current_user.user_id, query_date)

    # Serialize
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

    # Cache for 5 minutes
    await CacheManager.set(cache_key, response_data, ttl=CacheManager.TTL_SHORT)

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
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    POST /api/v1/users/{user_id}/tasks

    Creates a new task and returns its full representation.
    """
    _verify_user_ownership(current_user, user_id)

    task_service = TaskService(db)

    try:
        task = await task_service.create_task_v2(
            user_id=current_user.user_id,
            task_data=body,
        )
    except HighPriorityConflictError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "CONFLICT",
                "message": "A high-priority task already exists for this date",
            },
        )

    # Invalidate caches
    task_date = task.due_date.isoformat() if task.due_date else date.today().isoformat()
    await CacheManager.delete(CacheKeys.daily_tasks(str(user_id), task_date))
    await CacheManager.delete(CacheKeys.tasks_today(str(user_id)))

    return {
        "success": True,
        "data": _task_to_api(task),
    }


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
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    POST /api/v1/users/{user_id}/tasks/batch

    Creates tasks in bulk and returns a summary with the created task list.
    """
    _verify_user_ownership(current_user, user_id)

    # Parse date
    task_date = (
        date.fromisoformat(body.date) if body.date else date.today()
    )

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
            detail={
                "code": "VALIDATION_ERROR",
                "message": str(exc),
            },
        )

    # Invalidate caches
    await CacheManager.delete(
        CacheKeys.daily_tasks(str(user_id), task_date.isoformat())
    )
    await CacheManager.delete(CacheKeys.tasks_today(str(user_id)))

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
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    PUT /api/v1/users/{user_id}/tasks/batch

    Accepts partial task updates. Only fields present in each task object are
    written; omitted fields keep their current values. Tasks not included in the
    array are left unchanged.

    If a task's priority is changed to "high", any existing high-priority task
    for the same date is automatically demoted to "medium".
    """
    _verify_user_ownership(current_user, user_id)

    # Parse date
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
            detail={
                "code": "CONFLICT",
                "message": str(exc),
            },
        )

    # Invalidate caches
    await CacheManager.delete(
        CacheKeys.daily_tasks(str(user_id), task_date.isoformat())
    )
    await CacheManager.delete(CacheKeys.tasks_today(str(user_id)))

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
    description="Updates a single task's status (e.g. pending → in_progress → completed).",
)
async def update_user_task_status(
    user_id: Annotated[uuid.UUID, Path(description="The authenticated user's ID")],
    task_id: Annotated[uuid.UUID, Path(description="The task to update")],
    body: UpdateTaskStatusRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    PATCH /api/v1/users/{user_id}/tasks/{task_id}

    Updates a single task field (primarily status). Used for
    "Begin Session" (→ in_progress), completion, and skipping.
    """
    _verify_user_ownership(current_user, user_id)

    task_service = TaskService(db)
    task = await task_service.get_task_by_id(task_id, current_user.user_id)

    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "NOT_FOUND",
                "message": "Task not found",
            },
        )

    task.status = body.status
    await db.flush()

    # Invalidate caches
    task_date = task.due_date.isoformat() if task.due_date else date.today().isoformat()
    await CacheManager.delete(CacheKeys.daily_tasks(str(user_id), task_date))
    await CacheManager.delete(CacheKeys.tasks_today(str(user_id)))

    return {
        "success": True,
        "data": _task_to_api(task),
    }


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
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    DELETE /api/v1/users/{user_id}/tasks/{task_id}

    Permanently deletes a task. Returns 204 No Content on success.
    """
    _verify_user_ownership(current_user, user_id)

    task_service = TaskService(db)
    task = await task_service.get_task_by_id(task_id, current_user.user_id)

    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "NOT_FOUND",
                "message": "Task not found",
            },
        )

    # Capture date before deletion for cache invalidation
    task_date = task.due_date.isoformat() if task.due_date else date.today().isoformat()

    await task_service.delete_task(task)

    # Invalidate caches
    await CacheManager.delete(CacheKeys.daily_tasks(str(user_id), task_date))
    await CacheManager.delete(CacheKeys.tasks_today(str(user_id)))
