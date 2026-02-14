"""
Webhooks API Endpoints
======================

Handles webhooks from external services (RevenueCat).

Authentication:
    RevenueCat sends the configured authorization token in the
    ``Authorization`` header. We compare it against REVENUECAT_WEBHOOK_SECRET.

Idempotency:
    Each RevenueCat event has a unique ``id``. We store processed event IDs
    in Redis (with TTL) to prevent duplicate processing.
"""

import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.cache import CacheInvalidator, CacheManager, get_redis
from app.services.revenuecat import RevenueCatService

logger = logging.getLogger(__name__)

router = APIRouter()

# Redis key prefix for webhook idempotency
_WEBHOOK_IDEM_PREFIX = "webhook:revenuecat:event:"
_WEBHOOK_IDEM_TTL = 86400 * 7  # 7 days


async def _is_event_processed(event_id: str) -> bool:
    """Check if a webhook event has already been processed."""
    try:
        client = await get_redis()
        key = f"{_WEBHOOK_IDEM_PREFIX}{event_id}"
        return await client.exists(key) > 0
    except Exception as exc:
        logger.warning("Redis idempotency check failed: %s", exc)
        return False


async def _mark_event_processed(event_id: str) -> None:
    """Mark a webhook event as processed in Redis."""
    try:
        client = await get_redis()
        key = f"{_WEBHOOK_IDEM_PREFIX}{event_id}"
        await client.setex(key, _WEBHOOK_IDEM_TTL, "1")
    except Exception as exc:
        logger.warning("Redis idempotency set failed: %s", exc)


@router.post("/revenuecat")
async def revenuecat_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    authorization: str = Header(default="", alias="Authorization"),
):
    """
    Handle RevenueCat webhook events.

    RevenueCat must be configured to send events to this endpoint with an
    Authorization header matching ``REVENUECAT_WEBHOOK_SECRET``.

    Events handled:
    - INITIAL_PURCHASE
    - RENEWAL
    - NON_RENEWING_PURCHASE
    - CANCELLATION
    - UNCANCELLATION
    - EXPIRATION
    - BILLING_ISSUE
    - PRODUCT_CHANGE
    - SUBSCRIPTION_PAUSED
    - TRANSFER
    - SUBSCRIBER_ALIAS (acknowledged, no-op)

    Returns 200 as quickly as possible (RevenueCat requires < 60s response).
    """
    revenuecat_service = RevenueCatService(db)

    # ── Verify authorization ──────────────────────────────────────────────
    if not revenuecat_service.verify_webhook_authorization(authorization):
        logger.warning("Unauthorized RevenueCat webhook attempt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook authorization",
        )

    # ── Parse payload ─────────────────────────────────────────────────────
    try:
        body = await request.body()
        payload = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.error("Invalid webhook payload: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        )

    # RevenueCat wraps the event data under the "event" key
    event = payload.get("event", {})
    event_type = event.get("type")
    app_user_id = event.get("app_user_id")
    event_id = event.get("id")

    if not event_type:
        logger.info("Webhook received with no event type, acknowledging")
        return {"received": True}

    logger.info(
        "Webhook received: type=%s user=%s event_id=%s",
        event_type,
        app_user_id,
        event_id,
    )

    # ── Idempotency check ─────────────────────────────────────────────────
    if event_id and await _is_event_processed(event_id):
        logger.info("Duplicate webhook event %s, skipping", event_id)
        return {"received": True, "duplicate": True}

    # ── Process event ─────────────────────────────────────────────────────
    try:
        subscription = await revenuecat_service.process_webhook_event(event)

        # Commit the transaction
        await db.commit()

        # Mark event as processed (after successful commit)
        if event_id:
            await _mark_event_processed(event_id)

        # Invalidate caches if subscription was updated
        if subscription:
            await CacheInvalidator.on_subscription_change(
                str(subscription.user_id)
            )

        logger.info(
            "Webhook processed: type=%s user=%s event_id=%s",
            event_type,
            app_user_id,
            event_id,
        )

    except Exception as e:
        logger.exception(
            "Webhook processing error: type=%s user=%s event_id=%s",
            event_type,
            app_user_id,
            event_id,
        )
        await db.rollback()
        # Return 500 so RevenueCat will retry
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing webhook",
        )

    return {"received": True}
