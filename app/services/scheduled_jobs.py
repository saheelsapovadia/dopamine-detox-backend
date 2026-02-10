"""
Scheduled Jobs
==============

Background tasks for maintenance operations:
- Subscription expiration checks
- Billing issue grace period handling
- RevenueCat sync
- Monthly journal limit reset
"""

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subscription import (
    Subscription,
    SubscriptionHistory,
    SubscriptionStatus,
    SubscriptionTier,
    SubscriptionEventType,
)
from app.services.cache import CacheInvalidator


class ScheduledJobService:
    """Service for scheduled background jobs."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def check_expired_subscriptions(self) -> dict:
        """
        Check for expired subscriptions and downgrade to free tier.
        
        Run daily at 00:00 UTC.
        
        Returns:
            Summary of processed subscriptions
        """
        now = datetime.now(timezone.utc)
        
        # Find expired subscriptions
        stmt = select(Subscription).where(
            and_(
                Subscription.status.in_([
                    SubscriptionStatus.ACTIVE,
                    SubscriptionStatus.CANCELLED,
                ]),
                Subscription.expires_at < now,
                Subscription.tier != SubscriptionTier.FREE,
            )
        )
        result = await self.db.execute(stmt)
        expired_subscriptions = result.scalars().all()
        
        processed = 0
        errors = []
        
        for subscription in expired_subscriptions:
            try:
                # Store previous values
                prev_tier = subscription.tier
                prev_status = subscription.status
                
                # Downgrade to free
                subscription.tier = SubscriptionTier.FREE
                subscription.status = SubscriptionStatus.EXPIRED
                
                # Create history entry
                history = SubscriptionHistory(
                    subscription_id=subscription.subscription_id,
                    user_id=subscription.user_id,
                    event_type=SubscriptionEventType.EXPIRATION,
                    previous_tier=prev_tier,
                    new_tier=SubscriptionTier.FREE,
                    previous_status=prev_status.value,
                    new_status="expired",
                )
                self.db.add(history)
                
                # Invalidate cache
                await CacheInvalidator.on_subscription_change(str(subscription.user_id))
                
                processed += 1
                
            except Exception as e:
                errors.append({
                    "subscription_id": str(subscription.subscription_id),
                    "error": str(e),
                })
        
        await self.db.flush()
        
        return {
            "job": "check_expired_subscriptions",
            "processed": processed,
            "errors": errors,
            "run_at": now.isoformat(),
        }

    async def check_billing_issues(self) -> dict:
        """
        Check subscriptions with billing issues past grace period.
        
        Run every 6 hours.
        Grace period: 3 days.
        
        Returns:
            Summary of processed subscriptions
        """
        now = datetime.now(timezone.utc)
        grace_period = timedelta(days=3)
        cutoff_date = now - grace_period
        
        # Find subscriptions with billing issues past grace period
        stmt = select(Subscription).where(
            and_(
                Subscription.status == SubscriptionStatus.BILLING_ISSUE,
                Subscription.updated_at < cutoff_date,
            )
        )
        result = await self.db.execute(stmt)
        billing_issue_subs = result.scalars().all()
        
        processed = 0
        
        for subscription in billing_issue_subs:
            prev_tier = subscription.tier
            
            # Downgrade to free
            subscription.tier = SubscriptionTier.FREE
            subscription.status = SubscriptionStatus.EXPIRED
            
            # Create history entry
            history = SubscriptionHistory(
                subscription_id=subscription.subscription_id,
                user_id=subscription.user_id,
                event_type=SubscriptionEventType.EXPIRATION,
                previous_tier=prev_tier,
                new_tier=SubscriptionTier.FREE,
                previous_status="billing_issue",
                new_status="expired",
                revenuecat_event_data={"reason": "billing_grace_period_expired"},
            )
            self.db.add(history)
            
            await CacheInvalidator.on_subscription_change(str(subscription.user_id))
            processed += 1
        
        await self.db.flush()
        
        return {
            "job": "check_billing_issues",
            "processed": processed,
            "run_at": now.isoformat(),
        }

    async def sync_revenuecat_subscriptions(self) -> dict:
        """
        Sync subscription status with RevenueCat for active premium users.
        
        Run hourly.
        
        Returns:
            Summary of synced subscriptions
        """
        from app.services.revenuecat import RevenueCatService
        
        now = datetime.now(timezone.utc)
        
        # Find active premium subscriptions with RevenueCat IDs
        stmt = select(Subscription).where(
            and_(
                Subscription.tier.in_([
                    SubscriptionTier.MONTHLY,
                    SubscriptionTier.ANNUAL,
                ]),
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.revenuecat_subscriber_id.isnot(None),
            )
        )
        result = await self.db.execute(stmt)
        subscriptions = result.scalars().all()
        
        synced = 0
        errors = []
        
        revenuecat_service = RevenueCatService(self.db)
        
        for subscription in subscriptions:
            try:
                subscriber_data = await revenuecat_service.get_subscriber(
                    subscription.revenuecat_subscriber_id
                )
                
                if subscriber_data:
                    subscription.last_revenuecat_sync = now
                    
                    # Check entitlements
                    entitlements = subscriber_data.get("entitlements", {})
                    subscription.revenuecat_entitlements = list(entitlements.keys())
                    
                    synced += 1
                    
            except Exception as e:
                errors.append({
                    "subscription_id": str(subscription.subscription_id),
                    "error": str(e),
                })
        
        await self.db.flush()
        
        return {
            "job": "sync_revenuecat_subscriptions",
            "synced": synced,
            "errors": errors,
            "run_at": now.isoformat(),
        }

    async def reset_monthly_journal_limits(self) -> dict:
        """
        Reset journal limit caches for free tier users.
        
        Run on first day of each month at 00:00 UTC.
        
        Returns:
            Summary of reset limits
        """
        from app.services.cache import CacheManager
        
        now = datetime.now(timezone.utc)
        
        # Get previous month key
        if now.month == 1:
            prev_month = f"{now.year - 1}-12"
        else:
            prev_month = f"{now.year}-{now.month - 1:02d}"
        
        # Delete all journal limit caches for previous month
        deleted = await CacheManager.delete_pattern(
            f"cache:journal:limit:*:{prev_month}"
        )
        
        return {
            "job": "reset_monthly_journal_limits",
            "deleted_cache_keys": deleted,
            "month_reset": prev_month,
            "run_at": now.isoformat(),
        }


# Job runner functions (can be called from scheduler like APScheduler or Celery)

async def run_daily_expiration_check(db: AsyncSession) -> dict:
    """Run daily subscription expiration check."""
    service = ScheduledJobService(db)
    return await service.check_expired_subscriptions()


async def run_billing_issue_check(db: AsyncSession) -> dict:
    """Run billing issue grace period check."""
    service = ScheduledJobService(db)
    return await service.check_billing_issues()


async def run_revenuecat_sync(db: AsyncSession) -> dict:
    """Run RevenueCat sync."""
    service = ScheduledJobService(db)
    return await service.sync_revenuecat_subscriptions()


async def run_monthly_limit_reset(db: AsyncSession) -> dict:
    """Run monthly journal limit reset."""
    service = ScheduledJobService(db)
    return await service.reset_monthly_journal_limits()
