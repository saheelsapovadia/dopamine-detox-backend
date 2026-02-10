"""
Validators
==========

Common validation utilities.
"""

import re
from typing import Optional

from app.core.errors import ValidationError


def validate_email(email: str) -> str:
    """
    Validate email format.
    
    Args:
        email: Email address to validate
        
    Returns:
        Validated email (lowercase)
        
    Raises:
        ValidationError: If email is invalid
    """
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    if not re.match(pattern, email):
        raise ValidationError(
            message="Invalid email format",
            field="email",
        )
    
    return email.lower()


def validate_password(password: str) -> str:
    """
    Validate password strength.
    
    Requirements:
    - Minimum 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one number
    
    Args:
        password: Password to validate
        
    Returns:
        Validated password
        
    Raises:
        ValidationError: If password is weak
    """
    if len(password) < 8:
        raise ValidationError(
            message="Password must be at least 8 characters long",
            field="password",
        )
    
    if not any(c.isupper() for c in password):
        raise ValidationError(
            message="Password must contain at least one uppercase letter",
            field="password",
        )
    
    if not any(c.islower() for c in password):
        raise ValidationError(
            message="Password must contain at least one lowercase letter",
            field="password",
        )
    
    if not any(c.isdigit() for c in password):
        raise ValidationError(
            message="Password must contain at least one number",
            field="password",
        )
    
    return password


def validate_audio_format(filename: str) -> str:
    """
    Validate audio file format.
    
    Args:
        filename: Filename to validate
        
    Returns:
        File extension (lowercase)
        
    Raises:
        ValidationError: If format is not supported
    """
    allowed_formats = ["mp3", "wav", "m4a", "ogg"]
    
    if not filename:
        raise ValidationError(
            message="Filename is required",
            field="audio_file",
        )
    
    ext = filename.split(".")[-1].lower()
    
    if ext not in allowed_formats:
        raise ValidationError(
            message=f"Unsupported audio format. Allowed: {', '.join(allowed_formats)}",
            field="audio_file",
        )
    
    return ext


def validate_file_size(
    size_bytes: int,
    max_size_mb: int = 10,
    field_name: str = "file",
) -> None:
    """
    Validate file size.
    
    Args:
        size_bytes: File size in bytes
        max_size_mb: Maximum size in MB
        field_name: Field name for error message
        
    Raises:
        ValidationError: If file is too large
    """
    max_bytes = max_size_mb * 1024 * 1024
    
    if size_bytes > max_bytes:
        raise ValidationError(
            message=f"File too large. Maximum size is {max_size_mb}MB",
            field=field_name,
        )


def validate_uuid(uuid_str: str, field_name: str = "id") -> str:
    """
    Validate UUID format.
    
    Args:
        uuid_str: UUID string to validate
        field_name: Field name for error message
        
    Returns:
        Validated UUID string
        
    Raises:
        ValidationError: If UUID is invalid
    """
    import uuid
    
    try:
        uuid.UUID(uuid_str)
        return uuid_str
    except ValueError:
        raise ValidationError(
            message=f"Invalid UUID format",
            field=field_name,
        )


def validate_date_not_future(
    date_value,
    field_name: str = "date",
) -> None:
    """
    Validate date is not in the future.
    
    Args:
        date_value: Date to validate
        field_name: Field name for error message
        
    Raises:
        ValidationError: If date is in the future
    """
    from datetime import date
    
    if date_value > date.today():
        raise ValidationError(
            message="Date cannot be in the future",
            field=field_name,
        )


def validate_timezone(tz_str: Optional[str]) -> Optional[str]:
    """
    Validate timezone string.
    
    Args:
        tz_str: Timezone string (e.g., "America/New_York")
        
    Returns:
        Validated timezone string or None
        
    Raises:
        ValidationError: If timezone is invalid
    """
    if tz_str is None:
        return None
    
    try:
        import zoneinfo
        zoneinfo.ZoneInfo(tz_str)
        return tz_str
    except Exception:
        # Fall back to checking common timezones
        common_timezones = [
            "UTC", "America/New_York", "America/Los_Angeles",
            "Europe/London", "Europe/Paris", "Asia/Tokyo",
            "Asia/Kolkata", "Australia/Sydney",
        ]
        
        if tz_str not in common_timezones:
            raise ValidationError(
                message="Invalid timezone",
                field="timezone",
            )
        
        return tz_str
