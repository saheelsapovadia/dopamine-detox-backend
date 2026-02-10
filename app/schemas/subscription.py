"""
Subscription Schemas
====================

Pydantic schemas for subscription management endpoints.
"""

from datetime import datetime
from typing import Any, Optional
import uuid

from pydantic import BaseModel, Field


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
