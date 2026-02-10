"""
RevenueCat Service
==================

Integration with RevenueCat for subscription management.
"""

import hashlib
import hmac
from datetime import datetime, timezone
from typing import Any, Optional
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.subscription import (
    Subscription,
    SubscriptionHistory,
    SubscriptionStatus,
    SubscriptionTier,
    SubscriptionEventType,
    Platform,
)


class RevenueCatService:
    """Service for RevenueCat operations."""
    
    BASE_URL = "https://api.revenuecat.com/v1"
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.api_key = settings.REVENUECAT_API_KEY
        self.webhook_secret = settings.REVENUECAT_WEBHOOK_SECRET
    
    async def get_subscriber(self, subscriber_id: str) -> Optional[dict]:
        """
        Fetch subscriber information from RevenueCat.
        
        Args:
            subscriber_id: RevenueCat subscriber ID
            
        Returns:
            Subscriber data from RevenueCat
        """
        if not self.api_key:
            return None
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.BASE_URL}/subscribers/{subscriber_id}",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                )
                
                if response.status_code == 200:
                    return response.json().get("subscriber")
                
                return None
            except Exception as e:
                print(f"RevenueCat API error: {e}")
                return None
    
    def verify_webhook_signature(
        self,
        payload: str,
        signature: str,
    ) -> bool:
        """
        Verify RevenueCat webhook signature.
        
        Args:
            payload: Raw request body
            signature: X-Revenuecat-Signature header value
            
        Returns:
            True if signature is valid
        """
        if not self.webhook_secret:
            return False
        
        expected_sig = hmac.new(
            self.webhook_secret.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()
        
        return hmac.compare_digest(expected_sig, signature)
    
    def map_tier_from_product(self, product_id: str) -> SubscriptionTier:
        """Map RevenueCat product ID to subscription tier."""
        if "annual" in product_id.lower():
            return SubscriptionTier.ANNUAL
        elif "monthly" in product_id.lower():
            return SubscriptionTier.MONTHLY
        return SubscriptionTier.FREE
    
    async def process_purchase(
        self,
        user_id: uuid.UUID,
        subscriber_id: str,
        product_id: str,
        platform: str,
    ) -> Subscription:
        """
        Process a subscription purchase.
        
        Args:
            user_id: User's UUID
            subscriber_id: RevenueCat subscriber ID
            product_id: Product identifier
            platform: Platform (ios, android, web)
            
        Returns:
            Updated subscription
        """
        # Get subscriber info from RevenueCat
        subscriber_data = await self.get_subscriber(subscriber_id)
        
        # Get existing subscription
        stmt = select(Subscription).where(Subscription.user_id == user_id)
        result = await self.db.execute(stmt)
        subscription = result.scalar_one_or_none()
        
        if subscription is None:
            # Create new subscription (shouldn't happen normally)
            subscription = Subscription(user_id=user_id)
            self.db.add(subscription)
        
        # Previous values for history
        prev_tier = subscription.tier
        prev_status = subscription.status.value if subscription.status else None
        
        # Update subscription
        tier = self.map_tier_from_product(product_id)
        subscription.tier = tier
        subscription.status = SubscriptionStatus.ACTIVE
        subscription.revenuecat_subscriber_id = subscriber_id
        subscription.platform = Platform(platform)
        subscription.product_identifier = product_id
        subscription.last_revenuecat_sync = datetime.now(timezone.utc)
        
        # Extract data from RevenueCat response if available
        if subscriber_data:
            subscription.revenuecat_original_app_user_id = subscriber_data.get(
                "original_app_user_id"
            )
            
            # Get entitlements
            entitlements = subscriber_data.get("entitlements", {})
            subscription.revenuecat_entitlements = list(entitlements.keys())
            
            # Get subscription details
            subscriptions = subscriber_data.get("subscriptions", {})
            if product_id in subscriptions:
                sub_data = subscriptions[product_id]
                
                if sub_data.get("expires_date"):
                    subscription.expires_at = datetime.fromisoformat(
                        sub_data["expires_date"].replace("Z", "+00:00")
                    )
                
                if sub_data.get("purchase_date"):
                    subscription.latest_purchase_date = datetime.fromisoformat(
                        sub_data["purchase_date"].replace("Z", "+00:00")
                    )
                    
                    if subscription.original_purchase_date is None:
                        subscription.original_purchase_date = subscription.latest_purchase_date
                
                subscription.auto_renew = sub_data.get("unsubscribe_detected_at") is None
        
        await self.db.flush()
        
        # Create history entry
        history = SubscriptionHistory(
            subscription_id=subscription.subscription_id,
            user_id=user_id,
            event_type=SubscriptionEventType.PURCHASE,
            previous_tier=prev_tier,
            new_tier=tier,
            previous_status=prev_status,
            new_status="active",
            revenuecat_event_data=subscriber_data,
        )
        self.db.add(history)
        await self.db.flush()
        
        return subscription
    
    async def process_webhook_event(
        self,
        event_data: dict,
    ) -> Optional[Subscription]:
        """
        Process a RevenueCat webhook event.
        
        Args:
            event_data: Webhook event payload
            
        Returns:
            Updated subscription if applicable
        """
        event_type = event_data.get("type")
        app_user_id = event_data.get("app_user_id")
        product_id = event_data.get("product_id")
        
        if not app_user_id:
            return None
        
        # Find subscription by RevenueCat ID or user ID
        stmt = select(Subscription).where(
            Subscription.revenuecat_subscriber_id == app_user_id
        )
        result = await self.db.execute(stmt)
        subscription = result.scalar_one_or_none()
        
        if subscription is None:
            # Try to find by original app user ID (our user_id)
            try:
                user_id = uuid.UUID(app_user_id)
                stmt = select(Subscription).where(Subscription.user_id == user_id)
                result = await self.db.execute(stmt)
                subscription = result.scalar_one_or_none()
            except ValueError:
                pass
        
        if subscription is None:
            return None
        
        # Process based on event type
        prev_tier = subscription.tier
        prev_status = subscription.status.value
        
        if event_type in ("INITIAL_PURCHASE", "RENEWAL"):
            subscription.status = SubscriptionStatus.ACTIVE
            subscription.tier = self.map_tier_from_product(product_id) if product_id else subscription.tier
            
            if event_data.get("expiration_at_ms"):
                subscription.expires_at = datetime.fromtimestamp(
                    event_data["expiration_at_ms"] / 1000,
                    tz=timezone.utc,
                )
            
            history_event = SubscriptionEventType.RENEWAL if event_type == "RENEWAL" else SubscriptionEventType.PURCHASE
            
        elif event_type == "CANCELLATION":
            subscription.status = SubscriptionStatus.CANCELLED
            subscription.auto_renew = False
            subscription.cancelled_at = datetime.now(timezone.utc)
            history_event = SubscriptionEventType.CANCELLATION
            
        elif event_type == "EXPIRATION":
            subscription.status = SubscriptionStatus.EXPIRED
            subscription.tier = SubscriptionTier.FREE
            history_event = SubscriptionEventType.EXPIRATION
            
        elif event_type == "BILLING_ISSUE":
            subscription.status = SubscriptionStatus.BILLING_ISSUE
            history_event = SubscriptionEventType.BILLING_ISSUE
            
        elif event_type == "PRODUCT_CHANGE":
            new_product = event_data.get("new_product_id", product_id)
            subscription.tier = self.map_tier_from_product(new_product)
            subscription.product_identifier = new_product
            
            # Determine if upgrade or downgrade
            tier_order = {"free": 0, "monthly": 1, "annual": 2}
            old_order = tier_order.get(prev_tier.value, 0)
            new_order = tier_order.get(subscription.tier.value, 0)
            
            history_event = (
                SubscriptionEventType.UPGRADE if new_order > old_order
                else SubscriptionEventType.DOWNGRADE
            )
            
        else:
            # Unknown event type
            return subscription
        
        subscription.last_revenuecat_sync = datetime.now(timezone.utc)
        await self.db.flush()
        
        # Create history entry
        history = SubscriptionHistory(
            subscription_id=subscription.subscription_id,
            user_id=subscription.user_id,
            event_type=history_event,
            previous_tier=prev_tier,
            new_tier=subscription.tier,
            previous_status=prev_status,
            new_status=subscription.status.value,
            price_paid=event_data.get("price"),
            currency=event_data.get("currency"),
            store_transaction_id=event_data.get("transaction_id"),
            revenuecat_event_data=event_data,
        )
        self.db.add(history)
        await self.db.flush()
        
        return subscription
