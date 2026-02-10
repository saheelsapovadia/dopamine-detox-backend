"""
Helper Functions
================

Common utility functions used across the application.
"""

import uuid
from datetime import datetime, timezone


def generate_uuid() -> uuid.UUID:
    """Generate a new UUID v4."""
    return uuid.uuid4()


def utc_now() -> datetime:
    """Get current UTC datetime with timezone info."""
    return datetime.now(timezone.utc)


def format_datetime(dt: datetime) -> str:
    """Format datetime to ISO 8601 string."""
    return dt.isoformat()


def parse_date(date_str: str) -> datetime:
    """Parse ISO 8601 date string to datetime."""
    return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
