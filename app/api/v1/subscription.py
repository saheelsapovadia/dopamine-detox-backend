"""
Subscription API Endpoints
==========================

Handles subscription packages, purchases, status, and management.
"""

import logging
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import CurrentUser
from app.core.feature_limits import FEATURE_LIMITS, get_feature_limits
from app.models.subscription import Subscription, SubscriptionStatus, SubscriptionTier
from app.schemas.subscription import (
    CancelRequest,
    CancelResponse,
    PackagesResponse,
    PurchaseRequest,
    PurchaseResponse,
    RestoreRequest,
    RestoreResponse,
    SubscriptionStatusResponse,
)
from app.services.cache import CacheInvalidator, CacheKeys, CacheManager
from app.services.revenuecat import RevenueCatService

logger = logging.getLogger(__name__)

router = APIRouter()


# Subscription packages definition
PACKAGES = [
    {
        "package_id": "free",
        "tier": "free",
        "name": "Free",
        "description": "Basic features to get started",
        "price": 0,
        "currency": "USD",
        "billing_period": "lifetime",
        "revenuecat_identifier": None,
        "features": [
            "1 journal entry per month",
            "Unlimited daily tasks",
            "Basic progress tracking",
        ],
        "limitations": [
            "No AI insights",
            "No voice transcription",
            "No advanced analytics",
            "Advertisement supported",
        ],
        "trial_available": False,
        "is_default": True,
    },
    {
        "package_id": "monthly_premium",
        "tier": "monthly",
        "name": "Monthly Premium",
        "description": "Full AI-powered experience",
        "price": 8.00,
        "currency": "USD",
        "billing_period": "monthly",
        "revenuecat_identifier": "rc_monthly_premium_800",
        "product_identifier": "monthly_premium_800",
        "features": [
            "Unlimited journal entries",
            "AI-powered insights & analysis",
            "Voice transcription",
            "Progress reports & analytics",
            "Ad-free experience",
            "Daily motivation & coaching",
        ],
        "trial_available": True,
        "trial_duration_days": 7,
    },
    {
        "package_id": "annual_premium",
        "tier": "annual",
        "name": "Annual Premium",
        "description": "Save 25% with yearly billing",
        "price": 70.00,
        "currency": "USD",
        "billing_period": "annual",
        "revenuecat_identifier": "rc_annual_premium_7000",
        "product_identifier": "annual_premium_7000",
        "features": [
            "All Monthly Premium features",
            "Priority customer support",
            "Early access to new features",
            "25% savings vs monthly ($96/year → $70/year)",
        ],
        "trial_available": True,
        "trial_duration_days": 7,
        "badge": "Best Value",
        "savings": {
            "percentage": 25,
            "amount": 26.00,
            "comparison": "vs Monthly ($8 × 12 = $96)",
        },
    },
]


@router.get(
    "/packages",
    response_model=PackagesResponse,
)
async def get_packages(
    current_user: CurrentUser,
    platform: str = Query(default="ios", pattern="^(ios|android|web)$"),
):
    """
    Get available subscription packages.
    """
    # Try cache
    cache_key = CacheKeys.packages(platform)
    cached = await CacheManager.get(cache_key)
    if cached:
        # Add current subscription info
        cached["current_subscription"] = await _get_current_subscription_info(
            current_user
        )
        return PackagesResponse(success=True, data=cached)

    # Build feature comparison
    feature_comparison = {
        tier: limits for tier, limits in FEATURE_LIMITS.items()
    }

    response_data = {
        "packages": PACKAGES,
        "current_subscription": await _get_current_subscription_info(
            current_user
        ),
        "feature_comparison": feature_comparison,
    }

    # Cache packages (without current_subscription)
    cache_data = {
        "packages": PACKAGES,
        "feature_comparison": feature_comparison,
    }
    await CacheManager.set(cache_key, cache_data, ttl=CacheManager.TTL_HOUR)

    return PackagesResponse(success=True, data=response_data)


async def _get_current_subscription_info(user) -> dict:
    """Get current subscription info for user."""
    if user.subscription:
        return {
            "tier": user.subscription.tier.value,
            "status": user.subscription.status.value,
            "expires_at": (
                user.subscription.expires_at.isoformat()
                if user.subscription.expires_at
                else None
            ),
        }
    return {
        "tier": "free",
        "status": "active",
        "expires_at": None,
    }


@router.post(
    "/purchase",
    response_model=PurchaseResponse,
)
async def purchase_subscription(
    purchase_data: PurchaseRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Verify and activate subscription purchase.

    The actual payment is handled by RevenueCat SDK on the client.
    This endpoint verifies the purchase and activates the subscription.
    """
    # Verify package exists
    package = next(
        (p for p in PACKAGES if p["package_id"] == purchase_data.package_id),
        None,
    )

    if package is None or package["tier"] == "free":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "SUB_001",
                "message": "Invalid subscription package",
            },
        )

    # Check if already has active premium subscription
    if current_user.subscription and current_user.subscription.is_premium:
        if current_user.subscription.status == SubscriptionStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "SUB_003",
                    "message": "Active subscription already exists",
                },
            )

    # Process purchase with RevenueCat
    revenuecat_service = RevenueCatService(db)

    subscription = await revenuecat_service.process_purchase(
        user_id=current_user.user_id,
        subscriber_id=purchase_data.revenuecat_subscriber_id,
        product_id=purchase_data.product_identifier,
        platform=purchase_data.platform,
    )

    await db.commit()

    # Invalidate caches
    await CacheInvalidator.on_subscription_change(str(current_user.user_id))

    # Get feature limits for new tier
    feature_limits = get_feature_limits(subscription.tier.value)

    return PurchaseResponse(
        success=True,
        data={
            "subscription": {
                "subscription_id": str(subscription.subscription_id),
                "user_id": str(subscription.user_id),
                "tier": subscription.tier.value,
                "status": subscription.status.value,
                "started_at": subscription.started_at.isoformat(),
                "expires_at": (
                    subscription.expires_at.isoformat()
                    if subscription.expires_at
                    else None
                ),
                "auto_renew": subscription.auto_renew,
                "platform": (
                    subscription.platform.value if subscription.platform else None
                ),
                "product_identifier": subscription.product_identifier,
            },
            "unlocked_features": feature_limits,
        },
        message="Subscription activated successfully",
    )


@router.get(
    "/status",
    response_model=SubscriptionStatusResponse,
)
async def get_subscription_status(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    force_refresh: bool = Query(default=False),
):
    """
    Get current subscription status.

    Use force_refresh=true to bypass cache and query RevenueCat directly.
    This will sync the local subscription data with RevenueCat's latest state.
    """
    user_id_str = str(current_user.user_id)

    # Try cache if not forcing refresh
    if not force_refresh:
        cached = await CacheManager.get(
            CacheKeys.subscription_status(user_id_str)
        )
        if cached:
            return SubscriptionStatusResponse(success=True, data=cached)

    subscription = current_user.subscription

    # Force-refresh: sync from RevenueCat and update local DB
    if force_refresh and subscription and subscription.revenuecat_subscriber_id:
        try:
            revenuecat_service = RevenueCatService(db)
            subscription = await revenuecat_service.sync_subscription(subscription)
            await db.commit()

            # Invalidate stale cache after sync
            await CacheInvalidator.on_subscription_change(user_id_str)
        except Exception as e:
            logger.error(
                "Failed to sync subscription from RevenueCat for user=%s: %s",
                user_id_str,
                e,
            )
            # Continue with local data

    # Build response
    if subscription is None or subscription.tier == SubscriptionTier.FREE:
        response_data = {
            "status": "active",
            "tier": "free",
            "started_at": (
                current_user.created_at.isoformat()
                if current_user.created_at
                else None
            ),
            "expires_at": None,
            "auto_renew": False,
            "is_in_trial": False,
            "revenuecat_subscriber_id": None,
            "platform": None,
            "feature_limits": get_feature_limits("free"),
            "upgrade_available": True,
            "recommended_tier": "annual",
        }
    else:
        response_data = {
            "status": subscription.status.value,
            "tier": subscription.tier.value,
            "started_at": (
                subscription.started_at.isoformat()
                if subscription.started_at
                else None
            ),
            "expires_at": (
                subscription.expires_at.isoformat()
                if subscription.expires_at
                else None
            ),
            "auto_renew": subscription.auto_renew,
            "is_in_trial": subscription.status == SubscriptionStatus.TRIAL,
            "trial_end_date": (
                subscription.trial_end_date.isoformat()
                if subscription.trial_end_date
                else None
            ),
            "cancelled_at": (
                subscription.cancelled_at.isoformat()
                if subscription.cancelled_at
                else None
            ),
            "revenuecat_subscriber_id": subscription.revenuecat_subscriber_id,
            "platform": (
                subscription.platform.value if subscription.platform else None
            ),
            "product_identifier": subscription.product_identifier,
            "price_paid": (
                float(subscription.price_paid) if subscription.price_paid else None
            ),
            "currency": subscription.currency,
            "original_purchase_date": (
                subscription.original_purchase_date.isoformat()
                if subscription.original_purchase_date
                else None
            ),
            "latest_purchase_date": (
                subscription.latest_purchase_date.isoformat()
                if subscription.latest_purchase_date
                else None
            ),
            "store_transaction_id": subscription.store_transaction_id,
            "billing_issues": (
                subscription.status == SubscriptionStatus.BILLING_ISSUE
            ),
            "active_entitlements": subscription.revenuecat_entitlements or [],
            "feature_limits": get_feature_limits(subscription.tier.value),
        }

    # Cache
    await CacheManager.set(
        CacheKeys.subscription_status(user_id_str),
        response_data,
        ttl=CacheManager.TTL_SHORT,
    )

    return SubscriptionStatusResponse(success=True, data=response_data)


@router.post(
    "/cancel",
    response_model=CancelResponse,
)
async def cancel_subscription(
    cancel_data: CancelRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Cancel subscription auto-renewal.

    User retains access until expiration date.
    Note: Actual cancellation should be done through the App Store / Play Store
    via the RevenueCat SDK. This endpoint records the intent on our backend.
    """
    subscription = current_user.subscription

    if subscription is None or subscription.tier == SubscriptionTier.FREE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "SUB_004",
                "message": "No active subscription to cancel",
            },
        )

    if subscription.status == SubscriptionStatus.CANCELLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "SUB_005",
                "message": "Subscription already cancelled",
            },
        )

    # Update subscription
    from datetime import datetime, timezone

    subscription.status = SubscriptionStatus.CANCELLED
    subscription.auto_renew = False
    subscription.cancelled_at = datetime.now(timezone.utc)

    await db.flush()
    await db.commit()

    # Invalidate caches
    await CacheInvalidator.on_subscription_change(str(current_user.user_id))

    # Calculate days remaining
    days_remaining = 0
    if subscription.expires_at:
        delta = subscription.expires_at.date() - date.today()
        days_remaining = max(0, delta.days)

    return CancelResponse(
        success=True,
        data={
            "subscription": {
                "subscription_id": str(subscription.subscription_id),
                "status": subscription.status.value,
                "tier": subscription.tier.value,
                "auto_renew": False,
                "expires_at": (
                    subscription.expires_at.isoformat()
                    if subscription.expires_at
                    else None
                ),
                "cancelled_at": subscription.cancelled_at.isoformat(),
                "days_remaining": days_remaining,
            },
            "message": (
                f"Your subscription will remain active until "
                f"{subscription.expires_at.strftime('%B %d, %Y') if subscription.expires_at else 'expiration'}. "
                f"You can reactivate anytime before then."
            ),
            "downgrade_info": {
                "downgrade_date": (
                    subscription.expires_at.isoformat()
                    if subscription.expires_at
                    else None
                ),
                "new_tier": "free",
                "features_to_lose": [
                    "Unlimited journals (limited to 1/month)",
                    "AI insights & analysis",
                    "Voice transcription",
                    "Ad-free experience",
                ],
            },
        },
        message="Subscription cancelled successfully",
    )


@router.post(
    "/restore",
    response_model=RestoreResponse,
)
async def restore_purchases(
    restore_data: RestoreRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Restore previous purchases from App Store / Play Store.

    The client should call ``Purchases.restorePurchases()`` first, then
    call this endpoint. We sync the latest subscriber state from RevenueCat
    and update the local subscription.
    """
    revenuecat_service = RevenueCatService(db)

    # Use the user's ID as the RevenueCat subscriber ID
    subscriber_id = str(current_user.user_id)

    # If user already has a RevenueCat subscriber ID, prefer that
    if (
        current_user.subscription
        and current_user.subscription.revenuecat_subscriber_id
    ):
        subscriber_id = current_user.subscription.revenuecat_subscriber_id

    subscription = await revenuecat_service.restore_purchases(
        user_id=current_user.user_id,
        subscriber_id=subscriber_id,
        platform=restore_data.platform,
    )

    if subscription is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "SUB_006",
                "message": "No previous purchases found to restore",
            },
        )

    await db.commit()

    # Invalidate caches
    await CacheInvalidator.on_subscription_change(str(current_user.user_id))

    return RestoreResponse(
        success=True,
        data={
            "restored": True,
            "subscription": {
                "tier": subscription.tier.value,
                "status": subscription.status.value,
                "expires_at": (
                    subscription.expires_at.isoformat()
                    if subscription.expires_at
                    else None
                ),
                "product_identifier": subscription.product_identifier,
                "original_purchase_date": (
                    subscription.original_purchase_date.isoformat()
                    if subscription.original_purchase_date
                    else None
                ),
                "auto_renew": subscription.auto_renew,
                "active_entitlements": subscription.revenuecat_entitlements or [],
                "feature_limits": get_feature_limits(subscription.tier.value),
            },
        },
        message="Subscription restored successfully",
    )
