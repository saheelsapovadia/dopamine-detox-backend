"""Add HomeScreen task fields (category v2, priority, status, duration, icon)

Revision ID: a1b2c3d4e5f6
Revises: 829c53f23756
Create Date: 2026-02-07 12:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "829c53f23756"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# New enum values
NEW_CATEGORY_VALUES = ("WORK", "PERSONAL", "HEALTH", "LEARNING", "OTHER")
OLD_CATEGORY_VALUES = ("NON_NEGOTIABLE", "IMPORTANT", "OPTIONAL")

STATUS_VALUES = ("pending", "in_progress", "completed", "skipped")
PRIORITY_VALUES = ("high", "medium", "low")
ICON_TYPE_VALUES = ("pages", "plant", "journal", "exercise", "code", "default")


def upgrade() -> None:
    """Upgrade database schema."""

    # ------------------------------------------------------------------
    # 1. Create new enum types
    # ------------------------------------------------------------------
    taskstatus_enum = sa.Enum(*STATUS_VALUES, name="taskstatus")
    taskstatus_enum.create(op.get_bind(), checkfirst=True)

    taskpriority_enum = sa.Enum(*PRIORITY_VALUES, name="taskpriority")
    taskpriority_enum.create(op.get_bind(), checkfirst=True)

    taskicontype_enum = sa.Enum(*ICON_TYPE_VALUES, name="taskicontype")
    taskicontype_enum.create(op.get_bind(), checkfirst=True)

    # ------------------------------------------------------------------
    # 2. Replace taskcategory enum: OLD → NEW
    #    PostgreSQL does not support ALTER TYPE … RENAME VALUE so we
    #    recreate the column with the new enum.
    # ------------------------------------------------------------------
    # Map old categories to new defaults for any existing rows
    op.execute(
        "ALTER TABLE tasks "
        "ALTER COLUMN category TYPE VARCHAR(20) USING category::text"
    )
    # Drop old enum type
    op.execute("DROP TYPE IF EXISTS taskcategory")

    # Create new enum type
    new_category_enum = sa.Enum(*NEW_CATEGORY_VALUES, name="taskcategory")
    new_category_enum.create(op.get_bind(), checkfirst=True)

    # Migrate existing data: map old values → new defaults
    op.execute(
        "UPDATE tasks SET category = 'WORK' WHERE category = 'NON_NEGOTIABLE'"
    )
    op.execute(
        "UPDATE tasks SET category = 'PERSONAL' WHERE category = 'IMPORTANT'"
    )
    op.execute(
        "UPDATE tasks SET category = 'OTHER' WHERE category = 'OPTIONAL'"
    )

    # Cast column back to enum
    op.execute(
        "ALTER TABLE tasks "
        "ALTER COLUMN category TYPE taskcategory "
        "USING category::taskcategory"
    )
    op.execute(
        "ALTER TABLE tasks ALTER COLUMN category SET DEFAULT 'OTHER'"
    )

    # ------------------------------------------------------------------
    # 3. Add new columns to tasks table
    # ------------------------------------------------------------------
    op.add_column(
        "tasks",
        sa.Column("subtitle", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "tasks",
        sa.Column(
            "priority",
            sa.Enum(*PRIORITY_VALUES, name="taskpriority", create_type=False),
            nullable=False,
            server_default="medium",
        ),
    )
    op.add_column(
        "tasks",
        sa.Column(
            "duration_mins",
            sa.Integer(),
            nullable=False,
            server_default="25",
        ),
    )
    op.add_column(
        "tasks",
        sa.Column(
            "icon_type",
            sa.Enum(*ICON_TYPE_VALUES, name="taskicontype", create_type=False),
            nullable=False,
            server_default="default",
        ),
    )
    op.add_column(
        "tasks",
        sa.Column(
            "status",
            sa.Enum(*STATUS_VALUES, name="taskstatus", create_type=False),
            nullable=False,
            server_default="pending",
        ),
    )

    # Sync status with existing completed flag
    op.execute(
        "UPDATE tasks SET status = 'completed' WHERE completed = true"
    )

    # ------------------------------------------------------------------
    # 4. Update indexes
    # ------------------------------------------------------------------
    # Drop the old completed-based index
    op.drop_index("idx_task_user_completed", table_name="tasks")

    # Create new indexes
    op.create_index(
        "idx_task_user_status",
        "tasks",
        ["user_id", "status", "due_date"],
    )
    op.create_index(
        "idx_task_user_priority_date",
        "tasks",
        ["user_id", "priority", "due_date"],
    )


def downgrade() -> None:
    """Downgrade database schema."""

    # Drop new indexes
    op.drop_index("idx_task_user_priority_date", table_name="tasks")
    op.drop_index("idx_task_user_status", table_name="tasks")

    # Recreate old index
    op.create_index(
        "idx_task_user_completed",
        "tasks",
        ["user_id", "completed", "due_date"],
    )

    # Drop new columns
    op.drop_column("tasks", "status")
    op.drop_column("tasks", "icon_type")
    op.drop_column("tasks", "duration_mins")
    op.drop_column("tasks", "priority")
    op.drop_column("tasks", "subtitle")

    # Revert category enum
    op.execute(
        "ALTER TABLE tasks "
        "ALTER COLUMN category TYPE VARCHAR(20) USING category::text"
    )
    op.execute("DROP TYPE IF EXISTS taskcategory")

    old_category_enum = sa.Enum(*OLD_CATEGORY_VALUES, name="taskcategory")
    old_category_enum.create(op.get_bind(), checkfirst=True)

    # Map new → old
    op.execute(
        "UPDATE tasks SET category = 'NON_NEGOTIABLE' WHERE category = 'WORK'"
    )
    op.execute(
        "UPDATE tasks SET category = 'IMPORTANT' WHERE category IN ('PERSONAL', 'HEALTH', 'LEARNING')"
    )
    op.execute(
        "UPDATE tasks SET category = 'OPTIONAL' WHERE category = 'OTHER'"
    )
    op.execute(
        "ALTER TABLE tasks "
        "ALTER COLUMN category TYPE taskcategory "
        "USING category::taskcategory"
    )

    # Drop new enum types
    op.execute("DROP TYPE IF EXISTS taskstatus")
    op.execute("DROP TYPE IF EXISTS taskpriority")
    op.execute("DROP TYPE IF EXISTS taskicontype")
