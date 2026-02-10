"""
Tasks API Endpoints
===================

Handles task CRUD operations, completion, and daily planning.
"""

from datetime import date
from typing import Annotated, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import CurrentUser
from app.schemas.task import (
    CreateTasksResponse,
    DeleteTaskResponse,
    TaskCreate,
    TaskResponse,
    TaskUpdate,
    TodayTasksResponse,
)
from app.services.cache import CacheInvalidator, CacheKeys, CacheManager
from app.services.task_service import TaskService

router = APIRouter()


def task_to_response(task) -> dict:
    """Convert task model to response dict."""
    return {
        "task_id": str(task.task_id),
        "title": task.title,
        "subtitle": task.subtitle,
        "description": task.description,
        "category": task.category.value,
        "priority": task.priority.value if task.priority else None,
        "duration_mins": task.duration_mins,
        "icon_type": task.icon_type.value if task.icon_type else None,
        "status": task.status.value if task.status else None,
        "order_index": task.order_index,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "created_at": task.created_at.isoformat(),
    }


@router.get(
    "/today",
    response_model=TodayTasksResponse,
)
async def get_today_tasks(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    include_completed: bool = Query(default=True),
):
    """
    Get all tasks for today grouped by category.
    """
    user_id_str = str(current_user.user_id)
    today = date.today()
    
    # Try cache first
    cache_key = CacheKeys.tasks_today(user_id_str)
    if include_completed:
        cached = await CacheManager.get(cache_key)
        if cached:
            return TodayTasksResponse(success=True, data=cached)
    
    task_service = TaskService(db)
    
    # Get tasks grouped by category
    grouped_tasks = await task_service.get_tasks_by_category(
        current_user.user_id,
        today,
        include_completed,
    )
    
    # Get or check if plan exists
    plan = await task_service.get_daily_plan(current_user.user_id, today)
    
    # Get stats
    stats = await task_service.get_today_task_stats(current_user.user_id)
    
    response_data = {
        "date": today.isoformat(),
        "plan_exists": plan is not None,
        "plan_id": str(plan.plan_id) if plan else None,
        "tasks_by_category": {
            category: [task_to_response(t) for t in tasks]
            for category, tasks in grouped_tasks.items()
        },
        "summary": {
            "total_tasks": stats["total"],
            "completed_tasks": stats["completed"],
            "completion_percentage": stats["percentage"],
        },
    }
    
    # Cache if including completed (full response)
    if include_completed:
        await CacheManager.set(cache_key, response_data, ttl=CacheManager.TTL_SHORT)
    
    return TodayTasksResponse(success=True, data=response_data)


@router.post(
    "",
    response_model=CreateTasksResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_task(
    task_data: TaskCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Create a new task.
    """
    task_service = TaskService(db)
    
    # Set default due date to today if not provided
    if task_data.due_date is None:
        task_data.due_date = date.today()
    
    task = await task_service.create_task(
        user_id=current_user.user_id,
        task_data=task_data,
    )
    
    # Invalidate cache
    await CacheManager.delete(CacheKeys.tasks_today(str(current_user.user_id)))
    
    return CreateTasksResponse(
        success=True,
        data=TaskResponse(**task_to_response(task)),
        message="Task created successfully",
    )


@router.get(
    "/{task_id}",
)
async def get_task(
    task_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get a specific task by ID.
    """
    task_service = TaskService(db)
    task = await task_service.get_task_by_id(task_id, current_user.user_id)
    
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "TASK_001",
                "message": "Task not found",
            },
        )
    
    return {
        "success": True,
        "data": task_to_response(task),
    }


@router.put(
    "/{task_id}",
)
async def update_task(
    task_id: uuid.UUID,
    task_data: TaskUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Update a task.
    """
    task_service = TaskService(db)
    task = await task_service.get_task_by_id(task_id, current_user.user_id)
    
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "TASK_001",
                "message": "Task not found",
            },
        )
    
    updated_task = await task_service.update_task(task, task_data)
    
    # Invalidate cache
    await CacheManager.delete(CacheKeys.tasks_today(str(current_user.user_id)))
    
    return {
        "success": True,
        "data": task_to_response(updated_task),
        "message": "Task updated successfully",
    }


@router.delete(
    "/{task_id}",
    response_model=DeleteTaskResponse,
)
async def delete_task(
    task_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Delete a task.
    """
    task_service = TaskService(db)
    task = await task_service.get_task_by_id(task_id, current_user.user_id)
    
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "TASK_001",
                "message": "Task not found",
            },
        )
    
    await task_service.delete_task(task)
    
    # Invalidate cache
    await CacheManager.delete(CacheKeys.tasks_today(str(current_user.user_id)))
    
    return DeleteTaskResponse(
        success=True,
        message="Task deleted successfully",
    )


@router.post(
    "/{task_id}/complete",
)
async def complete_task(
    task_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Mark a task as completed.
    
    Returns celebration message and progress update.
    """
    task_service = TaskService(db)
    task = await task_service.get_task_by_id(task_id, current_user.user_id)
    
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "TASK_001",
                "message": "Task not found",
            },
        )
    
    from app.models.task import TaskStatus
    if task.status == TaskStatus.COMPLETED:
        return {
            "success": True,
            "data": {
                "task_id": str(task.task_id),
                "title": task.title,
                "status": "completed",
                "message": "Task was already completed",
            },
        }
    
    result = await task_service.complete_task(task, current_user.user_id)
    
    # Invalidate caches
    today = date.today()
    await CacheInvalidator.on_task_complete(
        str(current_user.user_id),
        today.isoformat(),
    )
    
    return {
        "success": True,
        "data": {
            "task_id": str(result["task"].task_id),
            "title": result["task"].title,
            "status": "completed",
            "celebration": result["celebration"],
            "today_completed": result["today_completed"],
            "today_total": result["today_total"],
        },
        "message": "Task completed successfully",
    }


@router.post(
    "/{task_id}/uncomplete",
)
async def uncomplete_task(
    task_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Mark a task as incomplete.
    """
    task_service = TaskService(db)
    task = await task_service.get_task_by_id(task_id, current_user.user_id)
    
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "TASK_001",
                "message": "Task not found",
            },
        )
    
    updated_task = await task_service.uncomplete_task(task)
    
    # Invalidate cache
    await CacheManager.delete(CacheKeys.tasks_today(str(current_user.user_id)))
    
    return {
        "success": True,
        "data": task_to_response(updated_task),
        "message": "Task marked as incomplete",
    }


# =============================================================================
# Voice Planning Endpoints (Phase 11)
# =============================================================================

from fastapi import File, Form, UploadFile

from app.core.feature_limits import FeatureGate
from app.models.task import TaskCategory
from app.services.azure_storage import get_storage_service
from app.services.speech_to_text import get_speech_service
from app.services.gemini_llm import get_gemini_service


@router.post(
    "/plan-day",
)
async def plan_day_with_voice(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    audio_file: UploadFile = File(...),
    plan_date: date = Form(default=None),
    audio_duration_seconds: int = Form(default=0),
):
    """
    Plan the day with voice input.
    
    - Uploads audio to Azure Blob Storage
    - Transcribes using Google Speech-to-Text
    - Extracts tasks using Gemini AI
    - Returns tasks for user review (not saved yet)
    
    Requires premium subscription for voice transcription.
    """
    # Check premium feature access
    tier = "free"
    if current_user.subscription:
        tier = current_user.subscription.tier.value
    
    if tier == "free":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "FEATURE_LOCKED",
                "message": "Voice planning requires a premium subscription",
                "feature": "voice_transcription",
                "required_tier": "monthly",
                "upgrade_url": "/api/v1/subscription/packages",
            },
        )
    
    # Default to today if no date provided
    if plan_date is None:
        plan_date = date.today()
    
    # Check if plan already exists
    task_service = TaskService(db)
    existing_plan = await task_service.get_daily_plan(current_user.user_id, plan_date)
    
    if existing_plan and existing_plan.tasks:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "TASK_002",
                "message": "Daily plan already exists for this date",
                "plan_id": str(existing_plan.plan_id),
            },
        )
    
    # Read audio content
    audio_content = await audio_file.read()
    
    # Validate file size
    max_size = 10 * 1024 * 1024  # 10MB
    if len(audio_content) > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "code": "VOICE_001",
                "message": "Audio file too large. Maximum size is 10MB.",
            },
        )
    
    # Get file format
    filename = audio_file.filename or "audio.mp3"
    file_format = filename.split(".")[-1].lower()
    if file_format not in ["mp3", "wav", "m4a", "ogg"]:
        file_format = "mp3"
    
    # Create or get daily plan
    plan = await task_service.get_or_create_daily_plan(current_user.user_id, plan_date)
    
    # Upload to Azure Blob Storage
    storage_service = get_storage_service()
    upload_result = await storage_service.upload_voice_recording(
        user_id=str(current_user.user_id),
        file_content=audio_content,
        recording_type="plans",
        file_format=file_format,
        reference_id=str(plan.plan_id),
    )
    
    # Update plan with audio URL
    plan.voice_input_url = upload_result["sas_url"]
    
    # Transcribe audio
    speech_service = get_speech_service()
    transcription_result = await speech_service.transcribe_audio(
        audio_content=audio_content,
        language_code="en-US",
        audio_format=file_format,
    )
    
    if not transcription_result["success"]:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "VOICE_003",
                "message": "Transcription service unavailable",
                "error": transcription_result.get("error"),
            },
        )
    
    transcription = transcription_result["transcription"]
    plan.transcription = transcription
    
    # Extract tasks using Gemini
    gemini_service = get_gemini_service()
    extracted_tasks = await gemini_service.extract_tasks_from_transcription(transcription)
    
    await db.flush()
    
    return {
        "success": True,
        "data": {
            "plan_id": str(plan.plan_id),
            "date": plan_date.isoformat(),
            "transcription": transcription,
            "audio_url": upload_result["sas_url"],
            "extracted_tasks": extracted_tasks,
            "requires_confirmation": True,
            "created_at": plan.created_at.isoformat(),
        },
        "message": "Tasks extracted successfully. Please review and confirm.",
    }


@router.post(
    "/plan-day/confirm",
)
async def confirm_daily_plan(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    plan_id: uuid.UUID = Form(...),
    tasks: str = Form(...),  # JSON string of tasks array
):
    """
    Confirm and save the daily plan with reviewed tasks.
    
    After user reviews and edits extracted tasks, this saves them.
    """
    import json
    
    task_service = TaskService(db)
    
    # Get the plan
    plan = await task_service.get_daily_plan(current_user.user_id, None)
    
    # Find plan by ID
    from sqlalchemy import select
    from app.models.task import DailyPlan
    
    stmt = select(DailyPlan).where(
        DailyPlan.plan_id == plan_id,
        DailyPlan.user_id == current_user.user_id,
    )
    result = await db.execute(stmt)
    plan = result.scalar_one_or_none()
    
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "TASK_003",
                "message": "Plan not found",
            },
        )
    
    # Parse tasks JSON
    try:
        tasks_data = json.loads(tasks)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "TASK_004",
                "message": "Invalid tasks JSON",
            },
        )
    
    # Create tasks
    created_tasks = []
    for i, task_data in enumerate(tasks_data):
        from app.schemas.task import TaskCreate
        
        category = task_data.get("category", "OTHER")
        valid_categories = [c.value for c in TaskCategory]
        if category not in valid_categories:
            category = "OTHER"
        
        task_create = TaskCreate(
            title=task_data.get("title", "Untitled task")[:200],
            description=task_data.get("description"),
            category=TaskCategory(category),
            due_date=plan.date,
            order_index=task_data.get("order_index", i),
        )
        
        task = await task_service.create_task(
            user_id=current_user.user_id,
            task_data=task_create,
            plan_id=plan.plan_id,
        )
        created_tasks.append(task)
    
    # Invalidate cache
    await CacheManager.delete(CacheKeys.tasks_today(str(current_user.user_id)))
    
    return {
        "success": True,
        "data": {
            "plan_id": str(plan.plan_id),
            "date": plan.date.isoformat(),
            "tasks_saved": len(created_tasks),
            "tasks": [task_to_response(t) for t in created_tasks],
        },
        "message": "Daily plan saved successfully",
    }
