"""
Database Base Model
===================

Provides the base class for all SQLAlchemy models.
"""

from datetime import datetime
from typing import Any
import uuid

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """
    Base class for all database models.
    
    Provides common columns and functionality.
    """

    # Type annotation for class attributes
    type_annotation_map = {
        datetime: DateTime(timezone=True),
    }


class TimestampMixin:
    """
    Mixin that adds created_at and updated_at timestamps.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UUIDMixin:
    """
    Mixin that provides a UUID primary key.
    """

    @classmethod
    def generate_uuid(cls) -> uuid.UUID:
        """Generate a new UUID."""
        return uuid.uuid4()


def generate_uuid() -> uuid.UUID:
    """Generate a new UUID for default values."""
    return uuid.uuid4()
