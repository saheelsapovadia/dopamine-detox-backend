"""
Task Schemas
============

Pydantic schemas for task and daily plan endpoints.
"""

from datetime import date, datetime
from typing import Any, Optional
import uuid

from pydantic import BaseModel, Field

from app.models.task import TaskCategory, TaskIconType, TaskPriority, TaskStatus


# =============================================================================
# Request Schemas
# =============================================================================

class TaskCreate(BaseModel):
    """Request schema for creating a task (legacy endpoint)."""
    
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    category: TaskCategory = TaskCategory.OTHER
    due_date: Optional[date] = None
    order_index: int = 0


class TaskUpdate(BaseModel):
    """Request schema for updating a task."""
    
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    subtitle: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    category: Optional[TaskCategory] = None
    priority: Optional[TaskPriority] = None
    duration_mins: Optional[int] = Field(None, alias="durationMins", ge=1, le=480)
    icon_type: Optional[TaskIconType] = Field(None, alias="iconType")
    status: Optional[TaskStatus] = None
    due_date: Optional[date] = None
    order_index: Optional[int] = None

    class Config:
        populate_by_name = True


class CreateTaskRequest(BaseModel):
    """
    Request schema for creating a task via the new API.
    
    Maps to POST /api/v1/users/{userId}/tasks
    """
    
    title: str = Field(min_length=1, max_length=200)
    subtitle: Optional[str] = Field(None, max_length=200)
    category: TaskCategory
    priority: TaskPriority
    duration_mins: int = Field(alias="durationMins", ge=1, le=480)
    icon_type: TaskIconType = Field(default=TaskIconType.DEFAULT, alias="iconType")
    date: Optional[str] = Field(
        None,
        description="ISO date for the task (YYYY-MM-DD). Defaults to today.",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )

    class Config:
        populate_by_name = True


class BatchTaskItem(BaseModel):
    """Single task within a batch create request."""
    
    title: str = Field(min_length=1, max_length=200)
    subtitle: Optional[str] = Field(None, max_length=200)
    category: TaskCategory
    priority: TaskPriority
    duration_mins: int = Field(alias="durationMins", ge=1, le=480)
    icon_type: TaskIconType = Field(default=TaskIconType.DEFAULT, alias="iconType")

    class Config:
        populate_by_name = True


class BatchCreateTasksRequest(BaseModel):
    """
    Request schema for batch creating tasks.
    
    Maps to POST /api/v1/users/{userId}/tasks/batch
    """
    
    date: Optional[str] = Field(
        None,
        description="ISO date (YYYY-MM-DD). Defaults to today.",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )
    tasks: list[BatchTaskItem] = Field(min_length=1, max_length=20)


class UpdateTaskItem(BaseModel):
    """
    Single task within a batch update request.

    Merge semantics: only fields present are updated;
    omitted fields keep their current values.
    """

    id: str = Field(description="Existing task ID (UUID) to update")
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    subtitle: Optional[str] = Field(None, max_length=200)
    category: Optional[TaskCategory] = None
    priority: Optional[TaskPriority] = None
    duration_mins: Optional[int] = Field(None, alias="durationMins", ge=1, le=480)
    icon_type: Optional[TaskIconType] = Field(None, alias="iconType")

    class Config:
        populate_by_name = True


class BatchUpdateTasksRequest(BaseModel):
    """
    Request schema for batch updating tasks.

    Maps to PUT /api/v1/users/{userId}/tasks/batch
    """

    date: str = Field(
        description="ISO date of the tasks being updated (YYYY-MM-DD).",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )
    tasks: list[UpdateTaskItem] = Field(min_length=1, max_length=20)


class UpdateTaskStatusRequest(BaseModel):
    """
    Request schema for updating a single task's status.

    Maps to PATCH /api/v1/users/{userId}/tasks/{taskId}
    """

    status: TaskStatus


# =============================================================================
# Response Schemas
# =============================================================================

class TaskResponse(BaseModel):
    """Response schema for a single task."""
    
    task_id: uuid.UUID
    title: str
    subtitle: Optional[str] = None
    description: Optional[str] = None
    category: str
    priority: Optional[str] = None
    duration_mins: Optional[int] = None
    icon_type: Optional[str] = None
    status: Optional[str] = None
    order_index: int
    due_date: Optional[date] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class TaskApiResponse(BaseModel):
    """
    Response schema for a task in the new API format.
    
    Uses camelCase field names to match the frontend contract.
    """
    
    id: str
    userId: str
    title: str
    subtitle: Optional[str] = None
    category: str
    priority: str
    durationMins: int
    iconType: str
    status: str
    date: Optional[str] = None
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None


class DaySummary(BaseModel):
    """Day summary for the day selector pills."""
    
    date: str
    label: str
    isToday: bool
    isCompleted: bool
    totalTasks: int
    completedTasks: int


class DailyTasksData(BaseModel):
    """Data payload for the daily tasks response."""
    
    date: str
    hasTasks: bool
    priorityTask: Optional[TaskApiResponse] = None
    laterTasks: list[TaskApiResponse] = []
    daySummaries: list[DaySummary] = []


class BatchCreateData(BaseModel):
    """Data payload for the batch create response."""
    
    date: str
    created: int
    tasks: list[TaskApiResponse] = []


# =============================================================================
# Legacy Response Schemas (backward compat for existing endpoints)
# =============================================================================

class TaskCompletionResponse(BaseModel):
    """Response schema for task completion."""
    
    task_id: uuid.UUID
    title: str
    status: str
    celebration: dict[str, Any]
    today_completed: int
    today_total: int


class TasksByCategory(BaseModel):
    """Tasks grouped by category."""
    
    non_negotiable: list[TaskResponse] = []
    important: list[TaskResponse] = []
    optional: list[TaskResponse] = []


class TasksSummary(BaseModel):
    """Summary of task completion."""
    
    total_tasks: int
    completed_tasks: int
    completion_percentage: int


class TodayTasksResponse(BaseModel):
    """Response schema for today's tasks (legacy)."""
    
    success: bool = True
    data: dict[str, Any]


class DailyPlanResponse(BaseModel):
    """Response schema for a daily plan."""
    
    plan_id: uuid.UUID
    date: date
    transcription: Optional[str] = None
    completed: bool
    tasks: list[TaskResponse]
    created_at: datetime
    
    class Config:
        from_attributes = True


class CreateTasksResponse(BaseModel):
    """Response for task creation (legacy)."""
    
    success: bool = True
    data: TaskResponse
    message: str = "Task created successfully"


class DeleteTaskResponse(BaseModel):
    """Response for task deletion."""
    
    success: bool = True
    message: str = "Task deleted successfully"
