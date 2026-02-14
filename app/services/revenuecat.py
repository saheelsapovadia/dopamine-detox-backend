"""
RevenueCat Service
==================

Integration with RevenueCat for subscription management.

Handles:
- Subscriber info fetching via REST API
- Webhook event processing (all RevenueCat event types)
- Purchase verification and activation
- Subscription restore from app stores
- Subscription sync (force-refresh from RevenueCat)
"""

import logging
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

logger = logging.getLogger(__name__)


class RevenueCatService:
    """Service for RevenueCat operations."""

    BASE_URL = "https://api.revenuecat.com/v1"

    def __init__(self, db: AsyncSession):
        self.db = db
        self.api_key = settings.REVENUECAT_API_KEY
        self.webhook_secret = settings.REVENUECAT_WEBHOOK_SECRET

    # -------------------------------------------------------------------------
    # RevenueCat REST API
    # -------------------------------------------------------------------------

    def _get_headers(self) -> dict[str, str]:
        """Common headers for RevenueCat API calls."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def get_subscriber(self, subscriber_id: str) -> Optional[dict]:
        """
        Fetch subscriber information from RevenueCat.

        Args:
            subscriber_id: RevenueCat subscriber ID (usually our user_id).

        Returns:
            Subscriber data dict from RevenueCat, or None on failure.
        """
        if not self.api_key:
            logger.warning("RevenueCat API key not configured, skipping subscriber fetch")
            return None

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.BASE_URL}/subscribers/{subscriber_id}",
                    headers=self._get_headers(),
                    timeout=10.0,
                )

                if response.status_code == 200:
                    data = response.json()
                    return data.get("subscriber")

                logger.error(
                    "RevenueCat API returned status %d for subscriber %s: %s",
                    response.status_code,
                    subscriber_id,
                    response.text[:200],
                )
                return None
            except httpx.TimeoutException:
                logger.error("RevenueCat API timeout for subscriber %s", subscriber_id)
                return None
            except Exception as e:
                logger.error("RevenueCat API error for subscriber %s: %s", subscriber_id, e)
                return None

    # -------------------------------------------------------------------------
    # Webhook Authentication
    # -------------------------------------------------------------------------

    def verify_webhook_authorization(self, authorization_header: str) -> bool:
        """
        Verify RevenueCat webhook authorization header.

        RevenueCat sends the configured authorization token in the
        ``Authorization`` header of each webhook request.

        Args:
            authorization_header: Value of the Authorization header.

        Returns:
            True if the token matches our configured secret.
        """
        if not self.webhook_secret:
            logger.warning("REVENUECAT_WEBHOOK_SECRET not configured")
            return False

        # RevenueCat sends the token exactly as configured in the dashboard
        return authorization_header == self.webhook_secret

    # -------------------------------------------------------------------------
    # Product → Tier Mapping
    # -------------------------------------------------------------------------

    @staticmethod
    def map_tier_from_product(product_id: str) -> SubscriptionTier:
        """Map RevenueCat product ID to subscription tier."""
        if not product_id:
            return SubscriptionTier.FREE

        pid = product_id.lower()
        if "annual" in pid or "yearly" in pid:
            return SubscriptionTier.ANNUAL
        elif "monthly" in pid:
            return SubscriptionTier.MONTHLY
        return SubscriptionTier.FREE

    # -------------------------------------------------------------------------
    # Subscription Lookup Helpers
    # -------------------------------------------------------------------------

    async def _find_subscription(self, app_user_id: str) -> Optional[Subscription]:
        """
        Find a local Subscription by RevenueCat subscriber ID or user UUID.

        RevenueCat may send our user_id (UUID) as app_user_id, or it may send
        the RevenueCat-assigned subscriber ID that we stored previously.
        """
        # Try by RevenueCat subscriber ID first
        stmt = select(Subscription).where(
            Subscription.revenuecat_subscriber_id == app_user_id
        )
        result = await self.db.execute(stmt)
        subscription = result.scalar_one_or_none()

        if subscription is not None:
            return subscription

        # Try by user UUID (our user_id used as RevenueCat app_user_id)
        try:
            user_id = uuid.UUID(app_user_id)
            stmt = select(Subscription).where(Subscription.user_id == user_id)
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()
        except ValueError:
            return None

    # -------------------------------------------------------------------------
    # Purchase Processing
    # -------------------------------------------------------------------------

    async def process_purchase(
        self,
        user_id: uuid.UUID,
        subscriber_id: str,
        product_id: str,
        platform: str,
    ) -> Subscription:
        """
        Process a subscription purchase.

        Called from the ``/subscription/purchase`` endpoint after the client
        completes the purchase flow via the RevenueCat SDK.

        Args:
            user_id: User's UUID.
            subscriber_id: RevenueCat subscriber ID.
            product_id: Product identifier.
            platform: Platform (ios, android, web).

        Returns:
            Updated Subscription object.
        """
        # Get subscriber info from RevenueCat
        subscriber_data = await self.get_subscriber(subscriber_id)

        # Get existing subscription
        stmt = select(Subscription).where(Subscription.user_id == user_id)
        result = await self.db.execute(stmt)
        subscription = result.scalar_one_or_none()

        if subscription is None:
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
                        subscription.original_purchase_date = (
                            subscription.latest_purchase_date
                        )

                subscription.auto_renew = (
                    sub_data.get("unsubscribe_detected_at") is None
                )

                if sub_data.get("store_transaction_id"):
                    subscription.store_transaction_id = sub_data[
                        "store_transaction_id"
                    ]

                if sub_data.get("original_purchase_date"):
                    subscription.original_purchase_date = datetime.fromisoformat(
                        sub_data["original_purchase_date"].replace("Z", "+00:00")
                    )

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

        logger.info(
            "Purchase processed: user=%s tier=%s product=%s platform=%s",
            user_id,
            tier.value,
            product_id,
            platform,
        )

        return subscription

    # -------------------------------------------------------------------------
    # Restore Purchases
    # -------------------------------------------------------------------------

    async def restore_purchases(
        self,
        user_id: uuid.UUID,
        subscriber_id: str,
        platform: str,
    ) -> Optional[Subscription]:
        """
        Restore purchases by syncing subscriber data from RevenueCat.

        The client calls ``Purchases.restorePurchases()`` which syncs with the
        store, then calls our endpoint with the resulting subscriber ID.
        We fetch the latest state from RevenueCat and update locally.

        Args:
            user_id: User's UUID.
            subscriber_id: RevenueCat subscriber ID (usually same as user_id).
            platform: Platform (ios, android).

        Returns:
            Updated Subscription or None if no active subscription found.
        """
        subscriber_data = await self.get_subscriber(subscriber_id)

        if not subscriber_data:
            logger.info("No subscriber data found on restore for user=%s", user_id)
            return None

        entitlements = subscriber_data.get("entitlements", {})
        active_entitlements = {
            k: v for k, v in entitlements.items() if v.get("expires_date") is None
            or datetime.fromisoformat(
                v["expires_date"].replace("Z", "+00:00")
            ) > datetime.now(timezone.utc)
        }

        if not active_entitlements:
            logger.info(
                "No active entitlements on restore for user=%s", user_id
            )
            return None

        # Find or create local subscription
        stmt = select(Subscription).where(Subscription.user_id == user_id)
        result = await self.db.execute(stmt)
        subscription = result.scalar_one_or_none()

        if subscription is None:
            subscription = Subscription(user_id=user_id)
            self.db.add(subscription)

        prev_tier = subscription.tier
        prev_status = subscription.status.value if subscription.status else None

        # Determine tier from active subscriptions
        subscriptions_data = subscriber_data.get("subscriptions", {})
        active_product = None
        latest_expiry = None

        for product_id, sub_info in subscriptions_data.items():
            expires = sub_info.get("expires_date")
            if expires:
                exp_dt = datetime.fromisoformat(expires.replace("Z", "+00:00"))
                if exp_dt > datetime.now(timezone.utc):
                    if latest_expiry is None or exp_dt > latest_expiry:
                        latest_expiry = exp_dt
                        active_product = product_id

        if active_product:
            subscription.tier = self.map_tier_from_product(active_product)
            subscription.product_identifier = active_product
            subscription.expires_at = latest_expiry

            sub_info = subscriptions_data[active_product]
            subscription.auto_renew = (
                sub_info.get("unsubscribe_detected_at") is None
            )

            if sub_info.get("store_transaction_id"):
                subscription.store_transaction_id = sub_info["store_transaction_id"]

            if sub_info.get("original_purchase_date"):
                subscription.original_purchase_date = datetime.fromisoformat(
                    sub_info["original_purchase_date"].replace("Z", "+00:00")
                )

            if sub_info.get("purchase_date"):
                subscription.latest_purchase_date = datetime.fromisoformat(
                    sub_info["purchase_date"].replace("Z", "+00:00")
                )
        else:
            # Non-subscription entitlement (e.g. non-renewing purchase)
            subscription.tier = SubscriptionTier.MONTHLY  # default premium

        subscription.status = SubscriptionStatus.ACTIVE
        subscription.revenuecat_subscriber_id = subscriber_id
        subscription.revenuecat_original_app_user_id = subscriber_data.get(
            "original_app_user_id"
        )
        subscription.revenuecat_entitlements = list(entitlements.keys())
        subscription.platform = Platform(platform)
        subscription.last_revenuecat_sync = datetime.now(timezone.utc)

        await self.db.flush()

        # Create history
        history = SubscriptionHistory(
            subscription_id=subscription.subscription_id,
            user_id=user_id,
            event_type=SubscriptionEventType.REACTIVATION,
            previous_tier=prev_tier,
            new_tier=subscription.tier,
            previous_status=prev_status,
            new_status=subscription.status.value,
            revenuecat_event_data=subscriber_data,
        )
        self.db.add(history)
        await self.db.flush()

        logger.info(
            "Purchases restored: user=%s tier=%s product=%s",
            user_id,
            subscription.tier.value,
            subscription.product_identifier,
        )

        return subscription

    # -------------------------------------------------------------------------
    # Sync Subscription from RevenueCat
    # -------------------------------------------------------------------------

    async def sync_subscription(
        self,
        subscription: Subscription,
    ) -> Subscription:
        """
        Force-sync a local subscription with RevenueCat's latest data.

        Called from the status endpoint when ``force_refresh=true``.

        Args:
            subscription: Existing local subscription with a RevenueCat ID.

        Returns:
            Updated Subscription object.
        """
        subscriber_id = (
            subscription.revenuecat_subscriber_id
            or str(subscription.user_id)
        )
        subscriber_data = await self.get_subscriber(subscriber_id)

        if not subscriber_data:
            logger.warning(
                "Could not sync subscription for user=%s: no RevenueCat data",
                subscription.user_id,
            )
            return subscription

        entitlements = subscriber_data.get("entitlements", {})
        subscription.revenuecat_entitlements = list(entitlements.keys())
        subscription.revenuecat_original_app_user_id = subscriber_data.get(
            "original_app_user_id"
        )

        # Check if there are any active entitlements
        has_active_entitlement = False
        for ent_data in entitlements.values():
            expires = ent_data.get("expires_date")
            if expires is None:
                has_active_entitlement = True
                break
            exp_dt = datetime.fromisoformat(expires.replace("Z", "+00:00"))
            if exp_dt > datetime.now(timezone.utc):
                has_active_entitlement = True
                break

        # Sync subscription details from the product
        subscriptions_data = subscriber_data.get("subscriptions", {})
        product_id = subscription.product_identifier

        if product_id and product_id in subscriptions_data:
            sub_info = subscriptions_data[product_id]

            if sub_info.get("expires_date"):
                subscription.expires_at = datetime.fromisoformat(
                    sub_info["expires_date"].replace("Z", "+00:00")
                )

            subscription.auto_renew = (
                sub_info.get("unsubscribe_detected_at") is None
            )

            if sub_info.get("billing_issues_detected_at"):
                subscription.status = SubscriptionStatus.BILLING_ISSUE
            elif not has_active_entitlement:
                subscription.status = SubscriptionStatus.EXPIRED
                subscription.tier = SubscriptionTier.FREE
            elif sub_info.get("unsubscribe_detected_at"):
                subscription.status = SubscriptionStatus.CANCELLED
            else:
                subscription.status = SubscriptionStatus.ACTIVE

            if sub_info.get("store_transaction_id"):
                subscription.store_transaction_id = sub_info["store_transaction_id"]
        elif not has_active_entitlement:
            subscription.status = SubscriptionStatus.EXPIRED
            subscription.tier = SubscriptionTier.FREE

        subscription.last_revenuecat_sync = datetime.now(timezone.utc)
        await self.db.flush()

        logger.info(
            "Subscription synced: user=%s tier=%s status=%s",
            subscription.user_id,
            subscription.tier.value,
            subscription.status.value,
        )

        return subscription

    # -------------------------------------------------------------------------
    # Webhook Event Processing
    # -------------------------------------------------------------------------

    async def process_webhook_event(
        self,
        event_data: dict[str, Any],
    ) -> Optional[Subscription]:
        """
        Process a RevenueCat webhook event.

        Handles all event types:
        - INITIAL_PURCHASE / RENEWAL / NON_RENEWING_PURCHASE
        - CANCELLATION / UNCANCELLATION
        - EXPIRATION
        - BILLING_ISSUE
        - PRODUCT_CHANGE
        - SUBSCRIPTION_PAUSED
        - TRANSFER
        - SUBSCRIBER_ALIAS (no-op)

        Args:
            event_data: The ``event`` object from the webhook payload.

        Returns:
            Updated Subscription if applicable, None otherwise.
        """
        event_type = event_data.get("type")
        app_user_id = event_data.get("app_user_id")
        product_id = event_data.get("product_id")

        if not app_user_id:
            logger.warning("Webhook event missing app_user_id: %s", event_type)
            return None

        # Find the local subscription
        subscription = await self._find_subscription(app_user_id)

        if subscription is None:
            # If it's an initial purchase, try to create from our user_id
            if event_type == "INITIAL_PURCHASE":
                return await self._handle_initial_purchase_new_user(event_data)

            logger.warning(
                "No subscription found for app_user_id=%s event=%s",
                app_user_id,
                event_type,
            )
            return None

        # Track previous state for history
        prev_tier = subscription.tier
        prev_status = subscription.status.value
        history_event: Optional[SubscriptionEventType] = None

        # ----- INITIAL_PURCHASE / RENEWAL -----
        if event_type in ("INITIAL_PURCHASE", "RENEWAL"):
            subscription.status = SubscriptionStatus.ACTIVE
            subscription.tier = (
                self.map_tier_from_product(product_id)
                if product_id
                else subscription.tier
            )

            if event_data.get("expiration_at_ms"):
                subscription.expires_at = datetime.fromtimestamp(
                    event_data["expiration_at_ms"] / 1000,
                    tz=timezone.utc,
                )

            if event_data.get("purchased_at_ms"):
                subscription.latest_purchase_date = datetime.fromtimestamp(
                    event_data["purchased_at_ms"] / 1000,
                    tz=timezone.utc,
                )

            if product_id:
                subscription.product_identifier = product_id

            subscription.auto_renew = True

            # If this is a trial conversion
            if event_data.get("is_trial_conversion"):
                subscription.trial_end_date = datetime.now(timezone.utc)

            if event_data.get("transaction_id"):
                subscription.store_transaction_id = event_data["transaction_id"]

            if event_data.get("original_transaction_id"):
                subscription.store_original_transaction_id = event_data[
                    "original_transaction_id"
                ]

            # Store entitlements from the event
            if event_data.get("entitlement_ids"):
                subscription.revenuecat_entitlements = event_data["entitlement_ids"]

            history_event = (
                SubscriptionEventType.RENEWAL
                if event_type == "RENEWAL"
                else SubscriptionEventType.PURCHASE
            )

            logger.info(
                "Webhook %s: user=%s product=%s",
                event_type,
                subscription.user_id,
                product_id,
            )

        # ----- NON_RENEWING_PURCHASE -----
        elif event_type == "NON_RENEWING_PURCHASE":
            subscription.status = SubscriptionStatus.ACTIVE
            subscription.tier = (
                self.map_tier_from_product(product_id)
                if product_id
                else subscription.tier
            )
            subscription.auto_renew = False

            if product_id:
                subscription.product_identifier = product_id

            if event_data.get("purchased_at_ms"):
                subscription.latest_purchase_date = datetime.fromtimestamp(
                    event_data["purchased_at_ms"] / 1000,
                    tz=timezone.utc,
                )

            if event_data.get("transaction_id"):
                subscription.store_transaction_id = event_data["transaction_id"]

            if event_data.get("entitlement_ids"):
                subscription.revenuecat_entitlements = event_data["entitlement_ids"]

            history_event = SubscriptionEventType.NON_RENEWING_PURCHASE

            logger.info(
                "Webhook NON_RENEWING_PURCHASE: user=%s product=%s",
                subscription.user_id,
                product_id,
            )

        # ----- CANCELLATION -----
        elif event_type == "CANCELLATION":
            subscription.status = SubscriptionStatus.CANCELLED
            subscription.auto_renew = False
            subscription.cancelled_at = datetime.now(timezone.utc)
            history_event = SubscriptionEventType.CANCELLATION

            logger.info(
                "Webhook CANCELLATION: user=%s, access until=%s",
                subscription.user_id,
                subscription.expires_at,
            )

        # ----- UNCANCELLATION -----
        elif event_type == "UNCANCELLATION":
            subscription.status = SubscriptionStatus.ACTIVE
            subscription.auto_renew = True
            subscription.cancelled_at = None
            history_event = SubscriptionEventType.UNCANCELLATION

            logger.info(
                "Webhook UNCANCELLATION: user=%s reactivated",
                subscription.user_id,
            )

        # ----- EXPIRATION -----
        elif event_type == "EXPIRATION":
            subscription.status = SubscriptionStatus.EXPIRED
            subscription.tier = SubscriptionTier.FREE
            subscription.auto_renew = False
            history_event = SubscriptionEventType.EXPIRATION

            logger.info(
                "Webhook EXPIRATION: user=%s downgraded to free",
                subscription.user_id,
            )

        # ----- BILLING_ISSUE -----
        elif event_type == "BILLING_ISSUE":
            subscription.status = SubscriptionStatus.BILLING_ISSUE
            history_event = SubscriptionEventType.BILLING_ISSUE

            logger.warning(
                "Webhook BILLING_ISSUE: user=%s product=%s",
                subscription.user_id,
                product_id,
            )

        # ----- PRODUCT_CHANGE -----
        elif event_type == "PRODUCT_CHANGE":
            new_product = event_data.get("new_product_id", product_id)
            old_tier = subscription.tier
            subscription.tier = self.map_tier_from_product(new_product)
            subscription.product_identifier = new_product

            if event_data.get("expiration_at_ms"):
                subscription.expires_at = datetime.fromtimestamp(
                    event_data["expiration_at_ms"] / 1000,
                    tz=timezone.utc,
                )

            # Determine if upgrade or downgrade
            tier_order = {"free": 0, "monthly": 1, "annual": 2}
            old_order = tier_order.get(old_tier.value, 0)
            new_order = tier_order.get(subscription.tier.value, 0)

            history_event = (
                SubscriptionEventType.UPGRADE
                if new_order > old_order
                else SubscriptionEventType.DOWNGRADE
            )

            logger.info(
                "Webhook PRODUCT_CHANGE: user=%s %s -> %s",
                subscription.user_id,
                old_tier.value,
                subscription.tier.value,
            )

        # ----- SUBSCRIPTION_PAUSED -----
        elif event_type == "SUBSCRIPTION_PAUSED":
            # Google Play only — subscription is paused, still active until pause takes effect
            subscription.auto_renew = False
            history_event = SubscriptionEventType.SUBSCRIPTION_PAUSED

            logger.info(
                "Webhook SUBSCRIPTION_PAUSED: user=%s",
                subscription.user_id,
            )

        # ----- TRANSFER -----
        elif event_type == "TRANSFER":
            # Subscription transferred to a different user
            new_app_user_id = event_data.get("transferred_to", [None])
            if isinstance(new_app_user_id, list) and new_app_user_id:
                new_app_user_id = new_app_user_id[0]

            history_event = SubscriptionEventType.TRANSFER

            logger.info(
                "Webhook TRANSFER: user=%s transferred to %s",
                subscription.user_id,
                new_app_user_id,
            )

        # ----- SUBSCRIBER_ALIAS / Unknown -----
        else:
            logger.info(
                "Webhook %s (no-op): app_user_id=%s",
                event_type,
                app_user_id,
            )
            return subscription

        # Update sync timestamp
        subscription.last_revenuecat_sync = datetime.now(timezone.utc)
        await self.db.flush()

        # Create history entry
        if history_event is not None:
            history = SubscriptionHistory(
                subscription_id=subscription.subscription_id,
                user_id=subscription.user_id,
                event_type=history_event,
                previous_tier=prev_tier,
                new_tier=subscription.tier,
                previous_status=prev_status,
                new_status=subscription.status.value,
                price_paid=event_data.get("price_in_purchased_currency"),
                currency=event_data.get("currency"),
                store_transaction_id=event_data.get("transaction_id"),
                revenuecat_event_data=event_data,
            )
            self.db.add(history)
            await self.db.flush()

        return subscription

    # -------------------------------------------------------------------------
    # Handle initial purchase when no subscription exists yet
    # -------------------------------------------------------------------------

    async def _handle_initial_purchase_new_user(
        self,
        event_data: dict[str, Any],
    ) -> Optional[Subscription]:
        """
        Handle INITIAL_PURCHASE for a user that doesn't have a subscription row yet.

        The ``app_user_id`` from RevenueCat should be our user UUID, so we
        create a new Subscription linked to that user.
        """
        app_user_id = event_data.get("app_user_id", "")
        product_id = event_data.get("product_id", "")

        try:
            user_id = uuid.UUID(app_user_id)
        except ValueError:
            # If it's not a UUID, try original_app_user_id
            original = event_data.get("original_app_user_id", "")
            try:
                user_id = uuid.UUID(original)
            except ValueError:
                logger.error(
                    "INITIAL_PURCHASE: cannot resolve user from app_user_id=%s or original=%s",
                    app_user_id,
                    original,
                )
                return None

        tier = self.map_tier_from_product(product_id)

        subscription = Subscription(
            user_id=user_id,
            tier=tier,
            status=SubscriptionStatus.ACTIVE,
            revenuecat_subscriber_id=app_user_id,
            revenuecat_original_app_user_id=event_data.get(
                "original_app_user_id"
            ),
            platform=self._parse_platform(event_data.get("store")),
            product_identifier=product_id,
            auto_renew=True,
            last_revenuecat_sync=datetime.now(timezone.utc),
        )

        if event_data.get("expiration_at_ms"):
            subscription.expires_at = datetime.fromtimestamp(
                event_data["expiration_at_ms"] / 1000,
                tz=timezone.utc,
            )

        if event_data.get("purchased_at_ms"):
            subscription.latest_purchase_date = datetime.fromtimestamp(
                event_data["purchased_at_ms"] / 1000,
                tz=timezone.utc,
            )
            subscription.original_purchase_date = subscription.latest_purchase_date

        if event_data.get("transaction_id"):
            subscription.store_transaction_id = event_data["transaction_id"]

        if event_data.get("original_transaction_id"):
            subscription.store_original_transaction_id = event_data[
                "original_transaction_id"
            ]

        if event_data.get("entitlement_ids"):
            subscription.revenuecat_entitlements = event_data["entitlement_ids"]

        self.db.add(subscription)
        await self.db.flush()

        # Create history
        history = SubscriptionHistory(
            subscription_id=subscription.subscription_id,
            user_id=user_id,
            event_type=SubscriptionEventType.PURCHASE,
            previous_tier=SubscriptionTier.FREE,
            new_tier=tier,
            previous_status="active",
            new_status="active",
            price_paid=event_data.get("price_in_purchased_currency"),
            currency=event_data.get("currency"),
            store_transaction_id=event_data.get("transaction_id"),
            revenuecat_event_data=event_data,
        )
        self.db.add(history)
        await self.db.flush()

        logger.info(
            "INITIAL_PURCHASE (new subscription): user=%s tier=%s product=%s",
            user_id,
            tier.value,
            product_id,
        )

        return subscription

    @staticmethod
    def _parse_platform(store: Optional[str]) -> Optional[Platform]:
        """Convert RevenueCat store string to Platform enum."""
        if not store:
            return None
        store_map = {
            "app_store": Platform.IOS,
            "play_store": Platform.ANDROID,
            "stripe": Platform.WEB,
            "mac_app_store": Platform.IOS,
            "amazon": Platform.ANDROID,
        }
        return store_map.get(store.lower())
