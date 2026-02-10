"""
Features API Endpoints
======================

Handles feature access checks and limit enforcement.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import CurrentUser
from app.core.feature_limits import (
    get_feature_limits,
    get_required_tier_for_feature,
    has_feature,
)
from app.schemas.subscription import FeatureCheckResponse, JournalLimitResponse
from app.services.cache import CacheKeys, CacheManager
from app.services.journal_service import JournalService

router = APIRouter()


@router.get(
    "/check",
    response_model=FeatureCheckResponse,
)
async def check_feature_access(
    current_user: CurrentUser,
    feature: str = Query(
        ...,
        description="Feature to check (ai_insights, voice_transcription, etc.)",
    ),
):
    """
    Check if user has access to a specific feature.
    """
    # Get user's tier
    tier = "free"
    if current_user.subscription:
        tier = current_user.subscription.tier.value
    
    # Check access
    has_access = has_feature(tier, feature)
    
    if has_access:
        return FeatureCheckResponse(
            success=True,
            data={
                "feature": feature,
                "has_access": True,
                "current_tier": tier,
            },
        )
    
    # Get required tier
    required_tier = get_required_tier_for_feature(feature)
    
    return FeatureCheckResponse(
        success=True,
        data={
            "feature": feature,
            "has_access": False,
            "current_tier": tier,
            "required_tier": required_tier,
            "reason": "This feature requires a premium subscription",
            "upgrade_url": "/subscription/packages",
        },
    )


@router.get(
    "/journal-limit",
    response_model=JournalLimitResponse,
)
async def check_journal_limit(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Check user's journal usage for current month.
    """
    user_id_str = str(current_user.user_id)
    
    # Get user's tier
    tier = "free"
    if current_user.subscription:
        tier = current_user.subscription.tier.value
    
    # Get feature limits
    limits = get_feature_limits(tier)
    journal_limit = limits.get("journals_per_month", 1)
    
    # For unlimited tiers
    if journal_limit == -1:
        return JournalLimitResponse(
            success=True,
            data={
                "tier": tier,
                "journals_this_month": 0,  # Not tracked for unlimited
                "journal_limit": -1,
                "remaining": "unlimited",
                "limit_reached": False,
                "can_create_journal": True,
            },
        )
    
    # Get current month's journal count
    today = date.today()
    month_key = f"{today.year}-{today.month:02d}"
    
    # Try cache
    cache_key = CacheKeys.journal_limit(user_id_str, month_key)
    cached_count = await CacheManager.get(cache_key)
    
    if cached_count is not None:
        journals_this_month = cached_count
    else:
        # Query database
        journal_service = JournalService(db)
        journals_this_month = await journal_service.get_entry_count_for_month(
            current_user.user_id,
            today.year,
            today.month,
        )
        
        # Cache the count
        await CacheManager.set(cache_key, journals_this_month, ttl=CacheManager.TTL_SHORT)
    
    remaining = max(0, journal_limit - journals_this_month)
    limit_reached = journals_this_month >= journal_limit
    
    # Calculate reset date (first of next month)
    if today.month == 12:
        reset_date = date(today.year + 1, 1, 1)
    else:
        reset_date = date(today.year, today.month + 1, 1)
    
    return JournalLimitResponse(
        success=True,
        data={
            "tier": tier,
            "journals_this_month": journals_this_month,
            "journal_limit": journal_limit,
            "remaining": remaining,
            "limit_reached": limit_reached,
            "reset_date": reset_date.isoformat() + "T00:00:00Z",
            "can_create_journal": not limit_reached,
            "upgrade_message": (
                "Upgrade to Premium for unlimited journal entries"
                if limit_reached else None
            ),
        },
    )


@router.get(
    "/all",
)
async def get_all_features(
    current_user: CurrentUser,
):
    """
    Get all feature limits for the user's current tier.
    """
    # Get user's tier
    tier = "free"
    if current_user.subscription:
        tier = current_user.subscription.tier.value
    
    # Get all limits
    limits = get_feature_limits(tier)
    
    return {
        "success": True,
        "data": {
            "tier": tier,
            "features": limits,
        },
    }
