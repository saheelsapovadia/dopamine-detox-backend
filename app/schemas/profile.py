"""
Profile Schemas
===============

Pydantic schemas for user profile endpoints.
"""

from datetime import datetime
from typing import Any, Optional
import uuid

from pydantic import BaseModel, EmailStr, Field


class NotificationPreferences(BaseModel):
    """Notification preferences schema."""
    
    notifications_enabled: bool = True
    daily_reminder_time: Optional[str] = "07:00"
    evening_reflection_time: Optional[str] = "20:00"
    voice_language: str = "en-US"


class ProfileUpdate(BaseModel):
    """Request schema for profile updates."""
    
    full_name: Optional[str] = Field(None, max_length=255)
    timezone: Optional[str] = Field(None, max_length=50)
    preferences: Optional[NotificationPreferences] = None


class SubscriptionInfo(BaseModel):
    """Subscription info for profile response."""
    
    tier: str
    status: str
    started_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    auto_renew: bool = False
    revenuecat_subscriber_id: Optional[str] = None
    
    class Config:
        from_attributes = True


class UserInfo(BaseModel):
    """User info for profile response."""
    
    user_id: uuid.UUID
    email: EmailStr
    full_name: Optional[str] = None
    created_at: datetime
    timezone: Optional[str] = "UTC"
    avatar_url: Optional[str] = None
    
    class Config:
        from_attributes = True


class ProfileResponse(BaseModel):
    """Response schema for profile endpoint."""
    
    success: bool = True
    data: dict[str, Any]


class ProfileData(BaseModel):
    """Profile data structure."""
    
    user: UserInfo
    subscription: SubscriptionInfo
    preferences: NotificationPreferences


class ProfileUpdateResponse(BaseModel):
    """Response schema for profile update."""
    
    success: bool = True
    data: dict[str, Any]
    message: str = "Profile updated successfully"
