"""
Subscription Schemas
====================

Pydantic schemas for subscription management endpoints.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
import uuid

from pydantic import BaseModel, Field


# ─── RevenueCat Webhook Event Types ──────────────────────────────────────────


class RevenueCatEventType(str, Enum):
    """All event types that RevenueCat can send via webhooks."""

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
    SUBSCRIBER_ALIAS = "SUBSCRIBER_ALIAS"


class RevenueCatEnvironment(str, Enum):
    """RevenueCat event environment."""

    PRODUCTION = "PRODUCTION"
    SANDBOX = "SANDBOX"


class RevenueCatWebhookEvent(BaseModel):
    """
    Pydantic model for a RevenueCat webhook event payload.

    Matches the ``event`` object inside the webhook body:
    ``{ "api_version": "1.0", "event": { ... } }``
    """

    id: str = Field(description="Unique event ID for idempotency")
    type: RevenueCatEventType
    app_user_id: str
    original_app_user_id: Optional[str] = None
    aliases: list[str] = Field(default_factory=list)
    product_id: Optional[str] = None
    period_type: Optional[str] = None
    purchased_at_ms: Optional[int] = None
    expiration_at_ms: Optional[int] = None
    environment: Optional[RevenueCatEnvironment] = None
    entitlement_ids: Optional[list[str]] = None
    entitlement_id: Optional[str] = None
    presented_offering_id: Optional[str] = None
    transaction_id: Optional[str] = None
    original_transaction_id: Optional[str] = None
    is_trial_conversion: Optional[bool] = None
    takehome_percentage: Optional[float] = None
    price_in_purchased_currency: Optional[float] = None
    currency: Optional[str] = None
    store: Optional[str] = None
    new_product_id: Optional[str] = None
    transferred_to: Optional[list[str]] = None

    class Config:
        use_enum_values = True


# ─── Feature & Package Schemas ───────────────────────────────────────────────


class FeatureLimits(BaseModel):
    """Feature limits for a subscription tier."""

    journals_per_month: int  # -1 for unlimited
    ai_insights: bool
    ai_analysis: bool
    voice_transcription: bool
    progress_reports: bool
    unlimited_tasks: bool
    ads_enabled: bool
    advanced_analytics: bool
    priority_support: bool


class SubscriptionPackage(BaseModel):
    """Subscription package information."""

    package_id: str
    tier: str
    name: str
    description: str
    price: float
    currency: str
    billing_period: str
    revenuecat_identifier: Optional[str] = None
    product_identifier: Optional[str] = None
    features: list[str]
    limitations: Optional[list[str]] = None
    trial_available: bool
    trial_duration_days: Optional[int] = None
    badge: Optional[str] = None
    savings: Optional[dict[str, Any]] = None
    is_default: bool = False


# ─── Request / Response Schemas ──────────────────────────────────────────────


class PackagesResponse(BaseModel):
    """Response schema for subscription packages."""

    success: bool = True
    data: dict[str, Any]


class PurchaseRequest(BaseModel):
    """Request schema for subscription purchase."""

    package_id: str
    revenuecat_subscriber_id: str
    platform: str = Field(pattern="^(ios|android|web)$")
    product_identifier: str


class PurchaseResponse(BaseModel):
    """Response schema for subscription purchase."""

    success: bool = True
    data: dict[str, Any]
    message: str = "Subscription activated successfully"


class SubscriptionStatusResponse(BaseModel):
    """Response schema for subscription status."""

    success: bool = True
    data: dict[str, Any]


class CancelRequest(BaseModel):
    """Request schema for subscription cancellation."""

    reason: Optional[str] = None
    feedback: Optional[str] = None


class CancelResponse(BaseModel):
    """Response schema for subscription cancellation."""

    success: bool = True
    data: dict[str, Any]
    message: str = "Subscription cancelled successfully"


class RestoreRequest(BaseModel):
    """Request schema for purchase restoration."""

    platform: str = Field(pattern="^(ios|android)$")


class RestoreResponse(BaseModel):
    """Response schema for purchase restoration."""

    success: bool = True
    data: dict[str, Any]
    message: str = "Subscription restored successfully"


class FeatureCheckResponse(BaseModel):
    """Response schema for feature access check."""

    success: bool = True
    data: dict[str, Any]


class JournalLimitResponse(BaseModel):
    """Response schema for journal limit check."""

    success: bool = True
    data: dict[str, Any]
