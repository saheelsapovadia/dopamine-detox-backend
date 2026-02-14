Now I have comprehensive information to provide you with a complete FastAPI backend integration guide. Here's how to integrate RevenueCat with your Python FastAPI backend:

Backend Integration with FastAPI
RevenueCat provides two main ways to integrate with your backend: Webhooks (for real-time event notifications) and REST API (for querying subscription status).

Setup FastAPI Project
First, install the required dependencies:

bash
pip install fastapi uvicorn httpx python-dotenv pydantic
Create your FastAPI application structure:

text
backend/
├── main.py
├── config.py
├── models.py
├── services/
│   └── revenuecat.py
└── routes/
    └── webhooks.py
Configuration
Create config.py for environment variables:

python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    REVENUECAT_API_KEY: str  # Your RevenueCat secret API key
    REVENUECAT_WEBHOOK_SECRET: str  # Custom authorization token
    REVENUECAT_API_URL: str = "https://api.revenuecat.com/v1"
    
    class Config:
        env_file = ".env"

settings = Settings()
Create .env file:

text
REVENUECAT_API_KEY=your_secret_api_key_here
REVENUECAT_WEBHOOK_SECRET=your_webhook_auth_token
Models
Create models.py to define Pydantic models for webhook events:

python
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum

class EventType(str, Enum):
    INITIAL_PURCHASE = "INITIAL_PURCHASE"
    RENEWAL = "RENEWAL"
    CANCELLATION = "CANCELLATION"
    UNCANCELLATION = "UNCANCELLATION"
    NON_RENEWING_PURCHASE = "NON_RENEWING_PURCHASE"
    SUBSCRIPTION_PAUSED = "SUBSCRIPTION_PAUSED"
    EXPIRATION = "EXPIRATION"
    BILLING_ISSUE = "BILLING_ISSUE"
    PRODUCT_CHANGE = "PRODUCT_CHANGE"
    TRANSFER = "TRANSFER"

class Environment(str, Enum):
    PRODUCTION = "PRODUCTION"
    SANDBOX = "SANDBOX"

class WebhookEvent(BaseModel):
    api_version: str
    event: EventType
    app_user_id: str
    original_app_user_id: str
    aliases: list[str] = []
    original_transaction_id: Optional[str] = None
    product_id: str
    period_type: str
    purchased_at_ms: int
    expiration_at_ms: Optional[int] = None
    environment: Environment
    entitlement_ids: Optional[list[str]] = None
    entitlement_id: Optional[str] = None
    presented_offering_id: Optional[str] = None
    transaction_id: Optional[str] = None
    original_purchase_date_ms: Optional[int] = None
    is_trial_conversion: Optional[bool] = None
    takehome_percentage: Optional[float] = None
    price_in_purchased_currency: Optional[float] = None
    currency: Optional[str] = None
    id: str  # Unique event ID for idempotency

class CustomerInfo(BaseModel):
    request_date: str
    request_date_ms: int
    subscriber: Dict[str, Any]
RevenueCat Service
Create services/revenuecat.py to handle API calls:
​

python
import httpx
from typing import Optional, Dict, Any
from config import settings
import logging

logger = logging.getLogger(__name__)

class RevenueCatService:
    def __init__(self):
        self.base_url = settings.REVENUECAT_API_URL
        self.api_key = settings.REVENUECAT_API_KEY
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Platform": "fastapi-backend"
        }
    
    async def get_subscriber_info(self, app_user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get subscriber information from RevenueCat API.
        Use this to verify subscription status for API requests.
        """
        url = f"{self.base_url}/subscribers/{app_user_id}"
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=self.headers, timeout=10.0)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                logger.error(f"Error fetching subscriber info: {e}")
                return None
    
    async def check_entitlement(self, app_user_id: str, entitlement_id: str) -> bool:
        """
        Check if user has an active entitlement.
        Returns True if user has active subscription.
        """
        subscriber_info = await self.get_subscriber_info(app_user_id)
        
        if not subscriber_info:
            return False
        
        entitlements = subscriber_info.get("subscriber", {}).get("entitlements", {})
        
        # Check if the specific entitlement exists and is active
        if entitlement_id in entitlements:
            expires_date = entitlements[entitlement_id].get("expires_date")
            # If expires_date is None, it's a lifetime entitlement
            if expires_date is None:
                return True
            # Check if not expired
            return expires_date is not None
        
        return False
    
    async def grant_promotional_entitlement(
        self, 
        app_user_id: str, 
        duration: str,
        entitlement_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Grant promotional entitlement to a user.
        Duration examples: "daily", "three_day", "weekly", "monthly", "two_month", 
                          "three_month", "six_month", "yearly", "lifetime"
        """
        url = f"{self.base_url}/subscribers/{app_user_id}/entitlements/{entitlement_id}/promotional"
        
        payload = {"duration": duration}
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, headers=self.headers, json=payload, timeout=10.0)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                logger.error(f"Error granting promotional entitlement: {e}")
                return None

# Singleton instance
revenuecat_service = RevenueCatService()
Webhook Handler
Create routes/webhooks.py:

python
from fastapi import APIRouter, Header, HTTPException, BackgroundTasks, Request
from models import WebhookEvent, EventType
from services.revenuecat import revenuecat_service
from config import settings
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

# Store processed event IDs to prevent duplicate processing
processed_events = set()  # In production, use Redis or database

async def process_webhook_event(event: WebhookEvent):
    """
    Background task to process webhook event.
    This runs after the 200 response is sent to RevenueCat.
    """
    logger.info(f"Processing event: {event.event} for user: {event.app_user_id}")
    
    # Get full subscriber info from RevenueCat API
    subscriber_info = await revenuecat_service.get_subscriber_info(event.original_app_user_id)
    
    if not subscriber_info:
        logger.error(f"Failed to fetch subscriber info for {event.original_app_user_id}")
        return
    
    # Extract subscription status
    entitlements = subscriber_info.get("subscriber", {}).get("entitlements", {})
    is_premium = len(entitlements) > 0
    
    # Update your database based on event type
    if event.event == EventType.INITIAL_PURCHASE:
        logger.info(f"New subscription for user {event.app_user_id}")
        # TODO: Update database - mark user as premium
        # await db.update_user(event.app_user_id, is_premium=True)
        
    elif event.event == EventType.RENEWAL:
        logger.info(f"Subscription renewed for user {event.app_user_id}")
        # TODO: Update subscription renewal date
        # await db.update_subscription_renewal(event.app_user_id, event.expiration_at_ms)
        
    elif event.event == EventType.CANCELLATION:
        logger.info(f"Subscription cancelled for user {event.app_user_id}")
        # TODO: Mark subscription as cancelled (but still active until expiration)
        # await db.mark_subscription_cancelled(event.app_user_id)
        
    elif event.event == EventType.EXPIRATION:
        logger.info(f"Subscription expired for user {event.app_user_id}")
        # TODO: Remove premium access
        # await db.update_user(event.app_user_id, is_premium=False)
        
    elif event.event == EventType.BILLING_ISSUE:
        logger.warning(f"Billing issue for user {event.app_user_id}")
        # TODO: Send notification to user about billing issue
        # await notification_service.send_billing_alert(event.app_user_id)
    
    logger.info(f"Event {event.id} processed successfully")

@router.post("/revenuecat/webhook")
async def handle_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    authorization: str = Header(None)
):
    """
    Webhook endpoint to receive RevenueCat events.
    Must return 200 status code within 60 seconds.
    """
    # Verify authorization header
    if authorization != settings.REVENUECAT_WEBHOOK_SECRET:
        logger.warning("Unauthorized webhook attempt")
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    # Parse webhook payload
    try:
        payload = await request.json()
        event = WebhookEvent(**payload)
    except Exception as e:
        logger.error(f"Invalid webhook payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload")
    
    # Check for duplicate events (idempotency)
    if event.id in processed_events:
        logger.info(f"Duplicate event {event.id} received, skipping")
        return {"status": "ok", "message": "duplicate event"}
    
    # Mark event as processed
    processed_events.add(event.id)
    
    # Process event in background to respond quickly
    background_tasks.add_task(process_webhook_event, event)
    
    # Return 200 immediately
    return {"status": "ok"}
Protected API Routes
Create middleware to verify subscription status for protected endpoints:
​

python
from fastapi import Depends, HTTPException, Header
from services.revenuecat import revenuecat_service
from typing import Optional

async def verify_subscription(
    x_app_user_id: str = Header(...),
    x_entitlement_id: str = Header(..., alias="X-Entitlement-ID")
) -> str:
    """
    Dependency to verify user has active subscription.
    Client should send App User ID in request header.
    """
    has_subscription = await revenuecat_service.check_entitlement(
        x_app_user_id, 
        x_entitlement_id
    )
    
    if not has_subscription:
        raise HTTPException(
            status_code=403, 
            detail="Active subscription required"
        )
    
    return x_app_user_id

# Example protected route
@router.get("/api/premium/content")
async def get_premium_content(user_id: str = Depends(verify_subscription)):
    """
    Protected endpoint that requires active subscription.
    """
    return {
        "message": "Premium content here",
        "user_id": user_id,
        "data": "Exclusive premium data..."
    }
Caching for Performance
Add caching to avoid hitting RevenueCat API on every request:
​

python
from functools import lru_cache
from datetime import datetime, timedelta
import asyncio

class SubscriptionCache:
    def __init__(self, ttl_seconds: int = 300):  # 5 minute cache
        self.cache = {}
        self.ttl = ttl_seconds
    
    def get(self, key: str) -> Optional[bool]:
        if key in self.cache:
            value, timestamp = self.cache[key]
            if datetime.now() - timestamp < timedelta(seconds=self.ttl):
                return value
            else:
                del self.cache[key]
        return None
    
    def set(self, key: str, value: bool):
        self.cache[key] = (value, datetime.now())

# Global cache instance
subscription_cache = SubscriptionCache()

async def verify_subscription_cached(
    x_app_user_id: str = Header(...),
    x_entitlement_id: str = Header(..., alias="X-Entitlement-ID")
) -> str:
    """
    Cached version of subscription verification.
    """
    cache_key = f"{x_app_user_id}:{x_entitlement_id}"
    
    # Check cache first
    cached_result = subscription_cache.get(cache_key)
    if cached_result is not None:
        if not cached_result:
            raise HTTPException(status_code=403, detail="Active subscription required")
        return x_app_user_id
    
    # Cache miss - check with RevenueCat
    has_subscription = await revenuecat_service.check_entitlement(
        x_app_user_id, 
        x_entitlement_id
    )
    
    # Store in cache
    subscription_cache.set(cache_key, has_subscription)
    
    if not has_subscription:
        raise HTTPException(status_code=403, detail="Active subscription required")
    
    return x_app_user_id
Main Application
Create main.py to bring it all together:

python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes.webhooks import router as webhook_router
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="RevenueCat Backend", version="1.0.0")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(webhook_router, tags=["webhooks"])

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
Client-Side Integration
In your React Native app, send the App User ID with API requests:

typescript
import Purchases from 'react-native-purchases';

// Get App User ID
const appUserId = await Purchases.getAppUserID();

// Make API request with user ID and entitlement
const response = await fetch('https://your-api.com/api/premium/content', {
  headers: {
    'X-App-User-ID': appUserId,
    'X-Entitlement-ID': 'premium',  // Your entitlement identifier
    'Content-Type': 'application/json'
  }
});
RevenueCat Dashboard Configuration
Configure the webhook in your RevenueCat dashboard:
​

Navigate to Project Settings → Integrations → Webhooks

Click Add new configuration

Enter your webhook URL: https://your-domain.com/revenuecat/webhook

Set the authorization header to match your REVENUECAT_WEBHOOK_SECRET

Select environment (Production, Sandbox, or Both)

(Optional) Filter specific events you want to receive