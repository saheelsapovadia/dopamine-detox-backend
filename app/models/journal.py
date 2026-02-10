"""
Journal Models
==============

SQLAlchemy models for journal entries, insights, and metrics.
"""

from datetime import date, datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional
import uuid

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
    Index,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class MoodRating(str, Enum):
    """Mood rating values."""
    GREAT = "great"  # 5
    GOOD = "good"  # 4
    CALM = "calm"  # 3
    STRESSED = "stressed"  # 2
    OVERWHELMED = "overwhelmed"  # 1


class InsightType(str, Enum):
    """Types of AI-generated insights."""
    ENERGETIC_MORNING = "energetic_morning"
    MIDDAY_STRESS = "midday_stress"
    EVENING_CALM = "evening_calm"
    PATTERN_DETECTED = "pattern_detected"
    EMOTIONAL_AWARENESS = "emotional_awareness"
    POSITIVE_BEHAVIOR = "positive_behavior"


class MetricType(str, Enum):
    """Types of daily metrics."""
    VOICE_INTENSITY = "voice_intensity"
    ENERGY_LEVEL = "energy_level"
    STRESS_LEVEL = "stress_level"


class JournalEntry(Base, TimestampMixin):
    """
    Journal entry model.
    
    Stores daily journal entries with voice transcriptions and mood tracking.
    """

    __tablename__ = "journal_entries"

    # Primary Key
    entry_id: Mapped[uuid.UUID] = mapped_column(
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

    # Entry details
    date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )
    entry_text: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # Voice recording fields
    voice_recording_url: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )
    transcription: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    is_voice_entry: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # Analysis fields
    mood_rating: Mapped[Optional[MoodRating]] = mapped_column(
        SQLEnum(MoodRating),
        nullable=True,
    )
    primary_emotion: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    secondary_emotions: Mapped[Optional[list]] = mapped_column(
        JSONB,
        nullable=True,
    )
    sentiment_score: Mapped[Optional[float]] = mapped_column(
        nullable=True,
    )
    summary: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="journal_entries",
    )
    insights: Mapped[list["JournalInsight"]] = relationship(
        "JournalInsight",
        back_populates="journal_entry",
        cascade="all, delete-orphan",
    )
    metrics: Mapped[list["DailyMetric"]] = relationship(
        "DailyMetric",
        back_populates="journal_entry",
        cascade="all, delete-orphan",
    )

    # Constraints and Indexes
    __table_args__ = (
        UniqueConstraint("user_id", "date", name="uq_journal_user_date"),
        Index("idx_journal_user_date", "user_id", "date"),
        Index("idx_journal_user_created", "user_id", "created_at"),
        Index("idx_journal_mood", "user_id", "mood_rating"),
    )

    def __repr__(self) -> str:
        return f"<JournalEntry(user_id={self.user_id}, date={self.date})>"


class JournalInsight(Base):
    """
    Journal insight model.
    
    Stores AI-generated insights from journal entries.
    """

    __tablename__ = "journal_insights"

    # Primary Key
    insight_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Foreign Key
    entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("journal_entries.entry_id", ondelete="CASCADE"),
        nullable=False,
    )

    # Insight details
    insight_type: Mapped[InsightType] = mapped_column(
        SQLEnum(InsightType),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    icon: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    color: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
    )

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    journal_entry: Mapped["JournalEntry"] = relationship(
        "JournalEntry",
        back_populates="insights",
    )

    def __repr__(self) -> str:
        return f"<JournalInsight(entry_id={self.entry_id}, type={self.insight_type})>"


class DailyMetric(Base):
    """
    Daily metric model.
    
    Tracks quantitative daily metrics for voice intensity and energy levels.
    """

    __tablename__ = "daily_metrics"

    # Primary Key
    metric_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Foreign Key
    entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("journal_entries.entry_id", ondelete="CASCADE"),
        nullable=False,
    )

    # Metric details
    metric_type: Mapped[MetricType] = mapped_column(
        SQLEnum(MetricType),
        nullable=False,
    )
    metric_values: Mapped[Optional[list]] = mapped_column(
        JSONB,
        nullable=True,  # For waveform data points
    )
    duration_seconds: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    journal_entry: Mapped["JournalEntry"] = relationship(
        "JournalEntry",
        back_populates="metrics",
    )

    def __repr__(self) -> str:
        return f"<DailyMetric(entry_id={self.entry_id}, type={self.metric_type})>"
