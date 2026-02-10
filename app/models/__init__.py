"""
Database Models
===============

SQLAlchemy ORM models for all database entities.

All models are imported here to ensure they are registered
with SQLAlchemy's metadata for migrations and relationships.
"""

from app.models.user import User
from app.models.subscription import (
    Subscription,
    SubscriptionHistory,
    SubscriptionTier,
    SubscriptionStatus,
    SubscriptionEventType,
    Platform,
)
from app.models.journal import (
    JournalEntry,
    JournalInsight,
    DailyMetric,
    MoodRating,
    InsightType,
    MetricType,
)
from app.models.task import (
    Task,
    DailyPlan,
    TaskCategory,
    TaskStatus,
    TaskPriority,
    TaskIconType,
)

__all__ = [
    # User
    "User",
    # Subscription
    "Subscription",
    "SubscriptionHistory",
    "SubscriptionTier",
    "SubscriptionStatus",
    "SubscriptionEventType",
    "Platform",
    # Journal
    "JournalEntry",
    "JournalInsight",
    "DailyMetric",
    "MoodRating",
    "InsightType",
    "MetricType",
    # Task
    "Task",
    "DailyPlan",
    "TaskCategory",
    "TaskStatus",
    "TaskPriority",
    "TaskIconType",
]
