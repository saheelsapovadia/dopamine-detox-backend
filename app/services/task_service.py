"""
Task Service
============

Business logic for task management, daily plans, and completion tracking.
"""

import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import Optional
import uuid

from sqlalchemy import case, func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.task import (
    DailyPlan,
    Task,
    TaskCategory,
    TaskIconType,
    TaskPriority,
    TaskStatus,
)
from app.schemas.task import (
    BatchTaskItem,
    CreateTaskRequest,
    TaskCreate,
    TaskUpdate,
    UpdateTaskItem,
)
class TaskService:
    """Service for task operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # =========================================================================
    # Core CRUD
    # =========================================================================

    async def get_task_by_id(
        self,
        task_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Optional[Task]:
        """Get task by ID ensuring it belongs to user."""
        stmt = select(Task).where(
            Task.task_id == task_id,
            Task.user_id == user_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create_task(
        self,
        user_id: uuid.UUID,
        task_data: TaskCreate,
        plan_id: Optional[uuid.UUID] = None,
    ) -> Task:
        """Create a new task (legacy endpoint)."""
        task = Task(
            user_id=user_id,
            plan_id=plan_id,
            title=task_data.title,
            description=task_data.description,
            category=task_data.category,
            due_date=task_data.due_date or date.today(),
            order_index=task_data.order_index,
        )
        self.db.add(task)
        await self.db.flush()
        return task

    async def create_task_v2(
        self,
        user_id: uuid.UUID,
        task_data: CreateTaskRequest,
    ) -> Task:
        """
        Create a new task via the v2 API.

        Enforces the constraint: only one high-priority task per date.
        """
        # Determine the task date
        task_date = (
            date.fromisoformat(task_data.date)
            if task_data.date
            else date.today()
        )

        # Enforce single high-priority task per date
        if task_data.priority == TaskPriority.HIGH:
            existing = await self._get_high_priority_task(user_id, task_date)
            if existing is not None:
                raise HighPriorityConflictError(task_date)

        task = Task(
            user_id=user_id,
            title=task_data.title,
            subtitle=task_data.subtitle,
            category=task_data.category,
            priority=task_data.priority,
            duration_mins=task_data.duration_mins,
            icon_type=task_data.icon_type,
            status=TaskStatus.PENDING,
            due_date=task_date,
        )
        self.db.add(task)
        await self.db.flush()
        return task

    async def batch_create_tasks(
        self,
        user_id: uuid.UUID,
        task_items: list[BatchTaskItem],
        task_date: date,
    ) -> list[Task]:
        """
        Batch-create tasks for a given date.

        Validates that at most one task has high priority.
        """
        # Check if there is already a high-priority task for this date
        high_count = sum(1 for t in task_items if t.priority == TaskPriority.HIGH)
        if high_count > 1:
            raise ValueError("Only one high-priority task is allowed per date")

        if high_count == 1:
            existing = await self._get_high_priority_task(user_id, task_date)
            if existing is not None:
                raise HighPriorityConflictError(task_date)

        created: list[Task] = []
        for i, item in enumerate(task_items):
            task = Task(
                user_id=user_id,
                title=item.title,
                subtitle=item.subtitle,
                category=item.category,
                priority=item.priority,
                duration_mins=item.duration_mins,
                icon_type=item.icon_type,
                status=TaskStatus.PENDING,
                due_date=task_date,
                order_index=i,
            )
            self.db.add(task)
            created.append(task)

        await self.db.flush()
        return created

    async def batch_update_tasks(
        self,
        user_id: uuid.UUID,
        task_items: list[UpdateTaskItem],
        task_date: date,
    ) -> list[Task]:
        """
        Batch-update tasks for a given date.

        Merge semantics:
        - Only fields present in each item are written.
        - Omitted fields retain their current values.
        - Tasks not listed in the array are left unchanged.

        Priority re-ranking:
        - If a task's priority is changed to ``high``, any *other* existing
          high-priority task for the same date is automatically demoted to
          ``medium``.

        Raises:
            TaskNotFoundError  – if any task ID doesn't exist for the user/date.
            ValueError         – if more than one task is set to high priority
                                 in the same request.
        """
        # Pre-validate: at most one high-priority in the request
        high_count = sum(
            1 for t in task_items if t.priority == TaskPriority.HIGH
        )
        if high_count > 1:
            raise ValueError("Only one task can have high priority per date")

        # Load requested tasks in one query
        task_ids = [uuid.UUID(t.id) for t in task_items]
        stmt = select(Task).where(
            Task.user_id == user_id,
            Task.due_date == task_date,
            Task.task_id.in_(task_ids),
        )
        result = await self.db.execute(stmt)
        tasks_by_id: dict[uuid.UUID, Task] = {
            t.task_id: t for t in result.scalars().all()
        }

        # Ensure every requested ID was found
        for item in task_items:
            tid = uuid.UUID(item.id)
            if tid not in tasks_by_id:
                raise TaskNotFoundError(item.id, task_date)

        # If any item sets priority to HIGH, demote the current high-priority
        # task (if it's a *different* task and not already in the update list).
        new_high_id: uuid.UUID | None = None
        for item in task_items:
            if item.priority == TaskPriority.HIGH:
                new_high_id = uuid.UUID(item.id)
                break

        if new_high_id is not None:
            existing_high = await self._get_high_priority_task(user_id, task_date)
            if (
                existing_high is not None
                and existing_high.task_id != new_high_id
            ):
                # Auto-demote the old high-priority task
                existing_high.priority = TaskPriority.MEDIUM

        # Apply partial updates
        updated: list[Task] = []
        for item in task_items:
            task = tasks_by_id[uuid.UUID(item.id)]
            if item.title is not None:
                task.title = item.title
            if item.subtitle is not None:
                task.subtitle = item.subtitle
            if item.category is not None:
                task.category = item.category
            if item.priority is not None:
                task.priority = item.priority
            if item.duration_mins is not None:
                task.duration_mins = item.duration_mins
            if item.icon_type is not None:
                task.icon_type = item.icon_type
            updated.append(task)

        await self.db.flush()

        # Refresh each task so server-generated columns (updated_at) are
        # eagerly loaded — avoids MissingGreenlet on lazy access in async.
        for task in updated:
            await self.db.refresh(task)

        return updated

    async def update_task(
        self,
        task: Task,
        task_data: TaskUpdate,
    ) -> Task:
        """Update an existing task."""
        if task_data.title is not None:
            task.title = task_data.title
        if task_data.subtitle is not None:
            task.subtitle = task_data.subtitle
        if task_data.description is not None:
            task.description = task_data.description
        if task_data.category is not None:
            task.category = task_data.category
        if task_data.priority is not None:
            task.priority = task_data.priority
        if task_data.duration_mins is not None:
            task.duration_mins = task_data.duration_mins
        if task_data.icon_type is not None:
            task.icon_type = task_data.icon_type
        if task_data.status is not None:
            task.status = task_data.status
        if task_data.due_date is not None:
            task.due_date = task_data.due_date
        if task_data.order_index is not None:
            task.order_index = task_data.order_index
        
        await self.db.flush()
        return task

    async def delete_task(self, task: Task) -> None:
        """Delete a task."""
        await self.db.delete(task)
        await self.db.flush()

    # =========================================================================
    # Daily Tasks (v2 API)
    # =========================================================================

    async def get_daily_tasks(
        self,
        user_id: uuid.UUID,
        target_date: date,
    ) -> dict:
        """
        Get the structured daily tasks payload for the HomeScreen.

        Optimised: runs the tasks query and the day-summaries aggregate
        **concurrently** and collapses 14+ sequential queries into just 2.

        Returns:
            {
                "date": "2026-02-07",
                "hasTasks": bool,
                "priorityTask": Task | None,
                "laterTasks": [Task, ...],
                "daySummaries": [DaySummary, ...],
            }
        """
        # Run both queries concurrently — they are independent reads.
        tasks, day_summaries = await asyncio.gather(
            self.get_tasks_for_date(user_id, target_date),
            self._build_day_summaries(user_id, target_date),
        )

        has_tasks = len(tasks) > 0
        priority_task: Optional[Task] = None
        later_tasks: list[Task] = []

        for task in tasks:
            if task.priority == TaskPriority.HIGH and priority_task is None:
                priority_task = task
            else:
                later_tasks.append(task)

        return {
            "date": target_date.isoformat(),
            "hasTasks": has_tasks,
            "priorityTask": priority_task,
            "laterTasks": later_tasks,
            "daySummaries": day_summaries,
        }

    async def _build_day_summaries(
        self,
        user_id: uuid.UUID,
        reference_date: date,
        num_days: int = 7,
    ) -> list[dict]:
        """
        Build day summary dicts for the day-selector pills.

        Optimised: a **single** GROUP BY query replaces the previous loop
        that fired 2 COUNT queries × 7 days = 14 round-trips.
        """
        dates = [reference_date - timedelta(days=i) for i in range(num_days)]
        today = date.today()
        weekday_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

        # Single aggregate query for all 7 dates
        stmt = (
            select(
                Task.due_date,
                func.count().label("total"),
                func.sum(
                    case(
                        (Task.status == TaskStatus.COMPLETED, 1),
                        else_=0,
                    )
                ).label("completed"),
            )
            .where(
                Task.user_id == user_id,
                Task.due_date.in_(dates),
            )
            .group_by(Task.due_date)
        )
        result = await self.db.execute(stmt)
        counts_by_date: dict[date, tuple[int, int]] = {
            row.due_date: (row.total, int(row.completed or 0))
            for row in result
        }

        summaries: list[dict] = []
        for d in dates:
            total, completed = counts_by_date.get(d, (0, 0))
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

    async def _task_counts_for_date(
        self,
        user_id: uuid.UUID,
        target_date: date,
    ) -> tuple[int, int]:
        """Return (total, completed) task counts for a user on a date.

        Optimised: single query with conditional aggregate instead of two
        separate COUNT queries.
        """
        stmt = (
            select(
                func.count().label("total"),
                func.sum(
                    case(
                        (Task.status == TaskStatus.COMPLETED, 1),
                        else_=0,
                    )
                ).label("completed"),
            )
            .select_from(Task)
            .where(Task.user_id == user_id, Task.due_date == target_date)
        )
        result = await self.db.execute(stmt)
        row = result.one()
        return row.total or 0, int(row.completed or 0)

    async def _get_high_priority_task(
        self,
        user_id: uuid.UUID,
        target_date: date,
    ) -> Optional[Task]:
        """Return the existing high-priority task for a date, if any."""
        stmt = select(Task).where(
            Task.user_id == user_id,
            Task.due_date == target_date,
            Task.priority == TaskPriority.HIGH,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    # =========================================================================
    # Legacy helpers (kept for backward compat with existing endpoints)
    # =========================================================================

    async def complete_task(
        self,
        task: Task,
        user_id: uuid.UUID,
    ) -> dict:
        """
        Mark task as completed.
        
        Returns celebration message and today's stats.
        """
        task.status = TaskStatus.COMPLETED
        
        # Get today's stats
        today = date.today()
        today_stats = await self.get_today_task_stats(user_id)
        
        await self.db.flush()
        
        # Generate celebration message
        celebration = self._generate_celebration(
            today_stats["completed"],
            today_stats["total"],
        )
        
        return {
            "task": task,
            "celebration": celebration,
            "today_completed": today_stats["completed"],
            "today_total": today_stats["total"],
        }

    async def uncomplete_task(self, task: Task) -> Task:
        """Mark task as incomplete."""
        task.status = TaskStatus.PENDING
        await self.db.flush()
        return task

    async def get_tasks_for_date(
        self,
        user_id: uuid.UUID,
        target_date: date,
        include_completed: bool = True,
    ) -> list[Task]:
        """Get all tasks for a specific date."""
        conditions = [
            Task.user_id == user_id,
            Task.due_date == target_date,
        ]
        
        if not include_completed:
            conditions.append(Task.status != TaskStatus.COMPLETED)
        
        stmt = (
            select(Task)
            .where(and_(*conditions))
            .order_by(Task.priority, Task.order_index)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_tasks_by_category(
        self,
        user_id: uuid.UUID,
        target_date: date,
        include_completed: bool = True,
    ) -> dict:
        """Get tasks grouped by category."""
        tasks = await self.get_tasks_for_date(user_id, target_date, include_completed)
        
        grouped: dict[str, list[Task]] = {}
        for cat in TaskCategory:
            grouped[cat.value] = []
        
        for task in tasks:
            grouped[task.category.value].append(task)
        
        return grouped

    async def get_today_task_stats(self, user_id: uuid.UUID) -> dict:
        """Get task statistics for today."""
        today = date.today()
        total, completed = await self._task_counts_for_date(user_id, today)
        
        return {
            "total": total,
            "completed": completed,
            "percentage": int((completed / total) * 100) if total > 0 else 0,
        }

    async def get_or_create_daily_plan(
        self,
        user_id: uuid.UUID,
        plan_date: date,
    ) -> DailyPlan:
        """Get existing daily plan or create new one."""
        stmt = select(DailyPlan).where(
            DailyPlan.user_id == user_id,
            DailyPlan.date == plan_date,
        ).options(selectinload(DailyPlan.tasks))
        
        result = await self.db.execute(stmt)
        plan = result.scalar_one_or_none()
        
        if plan is None:
            plan = DailyPlan(
                user_id=user_id,
                date=plan_date,
            )
            self.db.add(plan)
            await self.db.flush()
        
        return plan

    async def get_daily_plan(
        self,
        user_id: uuid.UUID,
        plan_date: date,
    ) -> Optional[DailyPlan]:
        """Get daily plan for a date."""
        stmt = (
            select(DailyPlan)
            .where(
                DailyPlan.user_id == user_id,
                DailyPlan.date == plan_date,
            )
            .options(selectinload(DailyPlan.tasks))
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    def _generate_celebration(
        self,
        today_completed: int,
        today_total: int,
    ) -> dict:
        """Generate celebration message based on completion."""
        messages = [
            {
                "message": "Beautifully done.",
                "sub_message": "Take a deep breath.",
                "icon": "star",
                "animation": "confetti",
            },
            {
                "message": "You're crushing it!",
                "sub_message": "Keep the momentum going.",
                "icon": "trophy",
                "animation": "sparkle",
            },
            {
                "message": "One step closer.",
                "sub_message": "Progress over perfection.",
                "icon": "growth",
                "animation": "pulse",
            },
            {
                "message": "Well done!",
                "sub_message": "Your future self thanks you.",
                "icon": "check",
                "animation": "bounce",
            },
        ]
        
        # Choose message based on completion count
        index = (today_completed - 1) % len(messages)
        celebration = messages[index].copy()
        
        # Add special message for completing all tasks
        if today_completed == today_total and today_total > 0:
            celebration = {
                "message": "All tasks complete!",
                "sub_message": "You've conquered the day.",
                "icon": "crown",
                "animation": "fireworks",
            }
        
        return celebration


# =============================================================================
# Custom Exceptions
# =============================================================================

class HighPriorityConflictError(Exception):
    """Raised when trying to create a second high-priority task for the same date."""

    def __init__(self, task_date: date):
        self.task_date = task_date
        super().__init__(
            f"A high-priority task already exists for {task_date.isoformat()}"
        )


class TaskNotFoundError(Exception):
    """Raised when a task ID is not found for the given user/date."""

    def __init__(self, task_id: str, task_date: date):
        self.task_id = task_id
        self.task_date = task_date
        super().__init__(
            f"Task {task_id} not found for date {task_date.isoformat()}"
        )
