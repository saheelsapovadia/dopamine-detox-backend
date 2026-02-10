"""
Feature Limits
==============

Feature limit definitions and enforcement middleware.
"""

from functools import wraps
from typing import Callable

from fastapi import HTTPException, status


# Feature limits by subscription tier
FEATURE_LIMITS = {
    "free": {
        "journals_per_month": 1,
        "ai_insights": False,
        "ai_analysis": False,
        "voice_transcription": False,
        "progress_reports": False,
        "unlimited_tasks": True,
        "ads_enabled": True,
        "advanced_analytics": False,
        "priority_support": False,
    },
    "monthly": {
        "journals_per_month": -1,  # Unlimited
        "ai_insights": True,
        "ai_analysis": True,
        "voice_transcription": True,
        "progress_reports": True,
        "unlimited_tasks": True,
        "ads_enabled": False,
        "advanced_analytics": True,
        "priority_support": False,
    },
    "annual": {
        "journals_per_month": -1,  # Unlimited
        "ai_insights": True,
        "ai_analysis": True,
        "voice_transcription": True,
        "progress_reports": True,
        "unlimited_tasks": True,
        "ads_enabled": False,
        "advanced_analytics": True,
        "priority_support": True,
    },
}


def get_feature_limits(tier: str) -> dict:
    """Get feature limits for a subscription tier."""
    return FEATURE_LIMITS.get(tier, FEATURE_LIMITS["free"])


def has_feature(tier: str, feature: str) -> bool:
    """Check if a tier has access to a specific feature."""
    limits = get_feature_limits(tier)
    return limits.get(feature, False)


def get_required_tier_for_feature(feature: str) -> str:
    """Get the minimum tier required for a feature."""
    # Check free tier
    if FEATURE_LIMITS["free"].get(feature):
        return "free"
    
    # Check monthly tier
    if FEATURE_LIMITS["monthly"].get(feature):
        return "monthly"
    
    # Must be annual-only
    return "annual"


class FeatureGate:
    """
    Feature gate for protecting endpoints based on subscription tier.
    
    Usage:
        @router.post("/endpoint")
        async def endpoint(
            current_user: CurrentUser,
            _: None = Depends(FeatureGate("ai_insights"))
        ):
            ...
    """
    
    def __init__(self, feature: str):
        self.feature = feature
    
    async def __call__(self, current_user) -> None:
        """Check if user has access to the feature."""
        # Get user's subscription tier
        tier = "free"
        if current_user.subscription:
            tier = current_user.subscription.tier.value
        
        # Check feature access
        if not has_feature(tier, self.feature):
            required_tier = get_required_tier_for_feature(self.feature)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "FEATURE_LOCKED",
                    "message": f"This feature requires a {required_tier} subscription",
                    "feature": self.feature,
                    "required_tier": required_tier,
                    "current_tier": tier,
                    "upgrade_url": "/api/v1/subscription/packages",
                },
            )


def require_feature(feature: str):
    """
    Decorator for requiring a specific feature.
    
    Usage:
        @require_feature("ai_insights")
        async def endpoint(current_user: CurrentUser):
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Find current_user in kwargs
            current_user = kwargs.get("current_user")
            if current_user is None:
                # Try to find in args (less common)
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required",
                )
            
            # Get tier
            tier = "free"
            if current_user.subscription:
                tier = current_user.subscription.tier.value
            
            # Check feature
            if not has_feature(tier, feature):
                required_tier = get_required_tier_for_feature(feature)
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "code": "FEATURE_LOCKED",
                        "message": f"This feature requires a {required_tier} subscription",
                        "feature": feature,
                        "required_tier": required_tier,
                        "current_tier": tier,
                    },
                )
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator
