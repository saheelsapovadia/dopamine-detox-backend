"""
Profile API Endpoints
=====================

Handles user profile retrieval and updates.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import CurrentUser
from app.models.user import User
from app.schemas.profile import (
    NotificationPreferences,
    ProfileResponse,
    ProfileUpdate,
    ProfileUpdateResponse,
    SubscriptionInfo,
    UserInfo,
)
from app.services.cache import CacheInvalidator, CacheKeys, CacheManager

router = APIRouter()


@router.get(
    "",
    response_model=ProfileResponse,
)
async def get_profile(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get complete user profile.
    
    Includes user info, subscription status, and preferences.
    """
    user_id_str = str(current_user.user_id)
    
    # Try cache first
    cached = await CacheManager.get(CacheKeys.profile(user_id_str))
    if cached:
        return ProfileResponse(success=True, data=cached)
    
    # Build response
    user_info = {
        "user_id": str(current_user.user_id),
        "email": current_user.email,
        "full_name": current_user.full_name,
        "created_at": current_user.created_at.isoformat(),
        "timezone": current_user.timezone,
        "avatar_url": current_user.avatar_url,
    }
    
    subscription_info = {
        "tier": "free",
        "status": "active",
        "started_at": None,
        "expires_at": None,
        "auto_renew": False,
        "revenuecat_subscriber_id": None,
    }
    
    if current_user.subscription:
        subscription_info = {
            "tier": current_user.subscription.tier.value,
            "status": current_user.subscription.status.value,
            "started_at": (
                current_user.subscription.started_at.isoformat()
                if current_user.subscription.started_at else None
            ),
            "expires_at": (
                current_user.subscription.expires_at.isoformat()
                if current_user.subscription.expires_at else None
            ),
            "auto_renew": current_user.subscription.auto_renew,
            "revenuecat_subscriber_id": current_user.subscription.revenuecat_subscriber_id,
        }
    
    # Parse notification preferences
    prefs = current_user.notification_preferences or {}
    preferences = {
        "notifications_enabled": prefs.get("notifications_enabled", True),
        "daily_reminder_time": prefs.get("daily_reminder_time", "07:00"),
        "evening_reflection_time": prefs.get("evening_reflection_time", "20:00"),
        "voice_language": prefs.get("voice_language", "en-US"),
    }
    
    profile_data = {
        "user": user_info,
        "subscription": subscription_info,
        "preferences": preferences,
    }
    
    # Cache the response
    await CacheManager.set(
        CacheKeys.profile(user_id_str),
        profile_data,
        ttl=CacheManager.TTL_SHORT,
    )
    
    return ProfileResponse(success=True, data=profile_data)


@router.put(
    "",
    response_model=ProfileUpdateResponse,
)
async def update_profile(
    profile_data: ProfileUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Update user profile.
    
    Allows updating name, timezone, and notification preferences.
    """
    # Update fields if provided
    if profile_data.full_name is not None:
        current_user.full_name = profile_data.full_name
    
    if profile_data.timezone is not None:
        current_user.timezone = profile_data.timezone
    
    if profile_data.preferences is not None:
        current_user.notification_preferences = profile_data.preferences.model_dump()
    
    await db.flush()
    
    # Invalidate cache
    await CacheInvalidator.on_profile_update(str(current_user.user_id))
    
    return ProfileUpdateResponse(
        success=True,
        data={
            "user_id": str(current_user.user_id),
            "full_name": current_user.full_name,
            "timezone": current_user.timezone,
            "updated_at": current_user.updated_at.isoformat(),
        },
        message="Profile updated successfully",
    )
