"""
Task Models
===========

SQLAlchemy models for tasks and daily plans.
"""

from datetime import date
from enum import Enum
from typing import TYPE_CHECKING, Optional
import uuid

from sqlalchemy import (
    Boolean,
    Date,
    Enum as SQLEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
    Index,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


# =============================================================================
# Enums
# =============================================================================

class TaskCategory(str, Enum):
    """Task category types."""
    WORK = "WORK"
    PERSONAL = "PERSONAL"
    HEALTH = "HEALTH"
    LEARNING = "LEARNING"
    OTHER = "OTHER"


class TaskStatus(str, Enum):
    """Task completion status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class TaskPriority(str, Enum):
    """Task priority level — determines card placement on HomeScreen."""
    HIGH = "high"       # Priority card (only one per day)
    MEDIUM = "medium"   # Later task list
    LOW = "low"         # Later task list


class TaskIconType(str, Enum):
    """Icon hint for the client."""
    PAGES = "pages"
    PLANT = "plant"
    JOURNAL = "journal"
    EXERCISE = "exercise"
    CODE = "code"
    DEFAULT = "default"


# =============================================================================
# Models
# =============================================================================

class DailyPlan(Base, TimestampMixin):
    """
    Daily plan model.
    
    Stores daily plans created through voice input.
    """

    __tablename__ = "daily_plans"

    # Primary Key
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Foreign Key
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )

    # Plan details
    date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )
    voice_input_url: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )
    transcription: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    parsed_goal: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    completed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="daily_plans",
    )
    tasks: Mapped[list["Task"]] = relationship(
        "Task",
        back_populates="daily_plan",
        cascade="all, delete-orphan",
        order_by="Task.order_index",
    )

    # Constraints and Indexes
    __table_args__ = (
        UniqueConstraint("user_id", "date", name="uq_plan_user_date"),
        Index("idx_plan_user_date", "user_id", "date"),
    )

    def __repr__(self) -> str:
        return f"<DailyPlan(user_id={self.user_id}, date={self.date})>"

    @property
    def completion_percentage(self) -> int:
        """Calculate task completion percentage."""
        if not self.tasks:
            return 0
        completed = sum(1 for task in self.tasks if task.status == TaskStatus.COMPLETED)
        return int((completed / len(self.tasks)) * 100)


class Task(Base, TimestampMixin):
    """
    Task model.
    
    Individual tasks created manually or extracted from daily plans.
    Maps to the HomeScreen priority card and later task list.
    """

    __tablename__ = "tasks"

    # Primary Key
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Foreign Keys
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    plan_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("daily_plans.plan_id", ondelete="SET NULL"),
        nullable=True,
    )

    # Task details
    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    subtitle: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    category: Mapped[TaskCategory] = mapped_column(
        SQLEnum(TaskCategory, name="taskcategory", create_constraint=True),
        nullable=False,
        default=TaskCategory.OTHER,
    )
    priority: Mapped[TaskPriority] = mapped_column(
        SQLEnum(TaskPriority, name="taskpriority", create_constraint=True, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=TaskPriority.MEDIUM,
    )
    duration_mins: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=25,
    )
    icon_type: Mapped[TaskIconType] = mapped_column(
        SQLEnum(TaskIconType, name="taskicontype", create_constraint=True, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=TaskIconType.DEFAULT,
    )
    status: Mapped[TaskStatus] = mapped_column(
        SQLEnum(TaskStatus, name="taskstatus", create_constraint=True, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=TaskStatus.PENDING,
    )
    order_index: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    due_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True,
    )

    # AI extraction metadata
    confidence_score: Mapped[Optional[float]] = mapped_column(
        nullable=True,
    )

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="tasks",
    )
    daily_plan: Mapped[Optional["DailyPlan"]] = relationship(
        "DailyPlan",
        back_populates="tasks",
    )

    # Indexes
    __table_args__ = (
        Index("idx_task_user_date", "user_id", "due_date"),
        Index("idx_task_plan_order", "plan_id", "order_index"),
        Index("idx_task_user_status", "user_id", "status", "due_date"),
        Index("idx_task_user_priority_date", "user_id", "priority", "due_date"),
    )

    def __repr__(self) -> str:
        return f"<Task(task_id={self.task_id}, title={self.title[:30]})>"

    def mark_complete(self) -> None:
        """Mark task as completed."""
        self.status = TaskStatus.COMPLETED

    def mark_incomplete(self) -> None:
        """Mark task as incomplete."""
        self.status = TaskStatus.PENDING

    def to_api_dict(self) -> dict:
        """
        Serialize to the API response format expected by the frontend.
        
        Maps internal field names to the API contract:
            task_id  → id
            due_date → date
            icon_type → iconType  (camelCase)
            duration_mins → durationMins
        """
        return {
            "id": str(self.task_id),
            "userId": str(self.user_id),
            "title": self.title,
            "subtitle": self.subtitle,
            "category": self.category.value,
            "priority": self.priority.value,
            "durationMins": self.duration_mins,
            "iconType": self.icon_type.value,
            "status": self.status.value,
            "date": self.due_date.isoformat() if self.due_date else None,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }
