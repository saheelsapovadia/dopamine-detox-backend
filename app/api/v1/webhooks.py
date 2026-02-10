"""
Webhooks API Endpoints
======================

Handles webhooks from external services (RevenueCat).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.cache import CacheInvalidator
from app.services.revenuecat import RevenueCatService

router = APIRouter()


@router.post(
    "/revenuecat",
)
async def revenuecat_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_revenuecat_signature: str = Header(default="", alias="X-Revenuecat-Signature"),
):
    """
    Handle RevenueCat webhook events.
    
    Events handled:
    - INITIAL_PURCHASE
    - RENEWAL
    - CANCELLATION
    - EXPIRATION
    - BILLING_ISSUE
    - PRODUCT_CHANGE
    """
    # Get raw body for signature verification
    body = await request.body()
    body_str = body.decode("utf-8")
    
    revenuecat_service = RevenueCatService(db)
    
    # Verify signature (in production)
    if x_revenuecat_signature:
        if not revenuecat_service.verify_webhook_signature(body_str, x_revenuecat_signature):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook signature",
            )
    
    # Parse payload
    try:
        import json
        payload = json.loads(body_str)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        )
    
    # Extract event data
    event = payload.get("event", {})
    event_type = event.get("type")
    app_user_id = event.get("app_user_id")
    
    if not event_type:
        # Unknown event, acknowledge but don't process
        return {"received": True}
    
    # Check idempotency (event already processed)
    event_id = event.get("id")
    # TODO: Implement idempotency check using Redis or database
    
    # Process event
    try:
        subscription = await revenuecat_service.process_webhook_event(event)
        
        # Invalidate caches if subscription was updated
        if subscription:
            await CacheInvalidator.on_subscription_change(str(subscription.user_id))
        
    except Exception as e:
        print(f"Webhook processing error: {e}")
        # Return 500 so RevenueCat will retry
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing webhook",
        )
    
    return {"received": True}
