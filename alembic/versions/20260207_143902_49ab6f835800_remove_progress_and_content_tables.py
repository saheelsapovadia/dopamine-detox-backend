"""Remove progress and content tables, simplify tasks and users

Removes 7 tables (user_progress, onboarding_steps, daily_checkins,
trigger_activities, affirmations, voice_recordings, system_messages)
and drops legacy columns from tasks (completed, completed_at) and
users (onboarding_completed).

Revision ID: 49ab6f835800
Revises: a1b2c3d4e5f6
Create Date: 2026-02-07 14:39:02.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "49ab6f835800"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # =========================================================================
    # Drop 7 tables
    # =========================================================================

    # Tables with FKs to other removed tables must be dropped first
    op.drop_table("daily_checkins")
    op.drop_table("onboarding_steps")
    op.drop_table("trigger_activities")
    op.drop_table("user_progress")
    op.drop_table("affirmations")
    op.drop_table("voice_recordings")
    op.drop_table("system_messages")

    # =========================================================================
    # Drop enum types used only by removed tables
    # =========================================================================
    op.execute("DROP TYPE IF EXISTS onboardingstepname")
    op.execute("DROP TYPE IF EXISTS checkinstatus")
    op.execute("DROP TYPE IF EXISTS triggercategory")
    op.execute("DROP TYPE IF EXISTS affirmationcategory")
    op.execute("DROP TYPE IF EXISTS messagecontext")
    op.execute("DROP TYPE IF EXISTS transcriptionstatus")

    # =========================================================================
    # Simplify tasks table: remove legacy columns
    # =========================================================================
    op.drop_column("tasks", "completed")
    op.drop_column("tasks", "completed_at")

    # =========================================================================
    # Simplify users table: remove onboarding_completed
    # =========================================================================
    op.drop_column("users", "onboarding_completed")


def downgrade() -> None:
    # =========================================================================
    # Re-add users.onboarding_completed
    # =========================================================================
    op.add_column(
        "users",
        sa.Column("onboarding_completed", sa.Boolean(), nullable=False, server_default="false"),
    )

    # =========================================================================
    # Re-add tasks legacy columns
    # =========================================================================
    op.add_column(
        "tasks",
        sa.Column("completed", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "tasks",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # =========================================================================
    # Re-create enum types
    # =========================================================================
    onboardingstepname = postgresql.ENUM(
        "breathing_exercise", "consistency_message", "progress_tracking",
        "momentum_building", "trigger_identification", "intentional_planning",
        name="onboardingstepname", create_type=True,
    )
    onboardingstepname.create(op.get_bind(), checkfirst=True)

    checkinstatus = postgresql.ENUM(
        "completed", "planned", "skipped",
        name="checkinstatus", create_type=True,
    )
    checkinstatus.create(op.get_bind(), checkfirst=True)

    triggercategory = postgresql.ENUM(
        "social_media", "food", "gaming", "shopping", "video", "other",
        name="triggercategory", create_type=True,
    )
    triggercategory.create(op.get_bind(), checkfirst=True)

    affirmationcategory = postgresql.ENUM(
        "encouragement", "progress", "mindfulness", "focus",
        name="affirmationcategory", create_type=True,
    )
    affirmationcategory.create(op.get_bind(), checkfirst=True)

    messagecontext = postgresql.ENUM(
        "welcome", "plan_start", "completion", "encouragement",
        name="messagecontext", create_type=True,
    )
    messagecontext.create(op.get_bind(), checkfirst=True)

    transcriptionstatus = postgresql.ENUM(
        "pending", "processing", "completed", "failed",
        name="transcriptionstatus", create_type=True,
    )
    transcriptionstatus.create(op.get_bind(), checkfirst=True)

    # =========================================================================
    # Re-create 7 tables
    # =========================================================================

    op.create_table(
        "user_progress",
        sa.Column("progress_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="CASCADE"), unique=True, nullable=False),
        sa.Column("total_tasks_completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_days_active", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_focus_streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("longest_focus_streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_journal_entries", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_active_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_user_progress_user_id", "user_progress", ["user_id"], unique=True)

    op.create_table(
        "onboarding_steps",
        sa.Column("step_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_name", onboardingstepname, nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("step_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("voice_recording_url", sa.String(500), nullable=True),
        sa.Column("transcription", sa.String(2000), nullable=True),
        sa.UniqueConstraint("user_id", "step_name", name="uq_onboarding_user_step"),
    )
    op.create_index("idx_onboarding_user", "onboarding_steps", ["user_id"])

    op.create_table(
        "daily_checkins",
        sa.Column("checkin_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("status", checkinstatus, nullable=False),
        sa.Column("completion_icon", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("user_id", "date", name="uq_checkin_user_date"),
    )
    op.create_index("idx_checkin_user_date", "daily_checkins", ["user_id", "date"])

    op.create_table(
        "trigger_activities",
        sa.Column("trigger_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("activity_name", sa.String(200), nullable=False),
        sa.Column("category", triggercategory, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("identified_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_trigger_user", "trigger_activities", ["user_id"])
    op.create_index("idx_trigger_user_active", "trigger_activities", ["user_id", "is_active"])

    op.create_table(
        "affirmations",
        sa.Column("affirmation_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="CASCADE"), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("category", affirmationcategory, nullable=False),
        sa.Column("is_system_affirmation", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_affirmation_user", "affirmations", ["user_id"])
    op.create_index("idx_affirmation_category", "affirmations", ["category", "is_system_affirmation"])

    op.create_table(
        "voice_recordings",
        sa.Column("recording_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_url", sa.String(500), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("format", sa.String(10), nullable=True),
        sa.Column("transcription_status", transcriptionstatus, nullable=False, server_default="pending"),
        sa.Column("transcription", sa.Text(), nullable=True),
        sa.Column("transcription_confidence", sa.Float(), nullable=True),
        sa.Column("recording_type", sa.String(50), nullable=True),
        sa.Column("reference_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_recording_user", "voice_recordings", ["user_id"])
    op.create_index("idx_recording_status", "voice_recordings", ["transcription_status"])
    op.create_index("idx_recording_reference", "voice_recordings", ["recording_type", "reference_id"])

    op.create_table(
        "system_messages",
        sa.Column("message_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("context", messagecontext, nullable=False),
        sa.Column("message_text", sa.Text(), nullable=False),
        sa.Column("icon", sa.String(50), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_system_message_context", "system_messages", ["context", "is_active"])
