"""
Subscription Models
===================

SQLAlchemy models for subscription management with RevenueCat integration.
"""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional
import uuid

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Numeric,
    String,
    Text,
    func,
    Index,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class SubscriptionTier(str, Enum):
    """Subscription tier levels."""
    FREE = "free"
    MONTHLY = "monthly"
    ANNUAL = "annual"


class SubscriptionStatus(str, Enum):
    """Subscription status values."""
    ACTIVE = "active"
    TRIAL = "trial"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    BILLING_ISSUE = "billing_issue"


class SubscriptionEventType(str, Enum):
    """Types of subscription events for history."""
    PURCHASE = "purchase"
    RENEWAL = "renewal"
    CANCELLATION = "cancellation"
    UNCANCELLATION = "uncancellation"
    EXPIRATION = "expiration"
    REACTIVATION = "reactivation"
    UPGRADE = "upgrade"
    DOWNGRADE = "downgrade"
    REFUND = "refund"
    BILLING_ISSUE = "billing_issue"
    SUBSCRIPTION_PAUSED = "subscription_paused"
    NON_RENEWING_PURCHASE = "non_renewing_purchase"
    TRANSFER = "transfer"
    PRODUCT_CHANGE = "product_change"


class Platform(str, Enum):
    """Purchase platform."""
    IOS = "ios"
    ANDROID = "android"
    WEB = "web"


class Subscription(Base, TimestampMixin):
    """
    Subscription model with RevenueCat integration.
    
    Stores user subscription information and RevenueCat data.
    """

    __tablename__ = "subscriptions"

    # Primary Key
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Foreign Key
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    # Subscription details
    tier: Mapped[SubscriptionTier] = mapped_column(
        SQLEnum(SubscriptionTier),
        default=SubscriptionTier.FREE,
        nullable=False,
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        SQLEnum(SubscriptionStatus),
        default=SubscriptionStatus.ACTIVE,
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,  # Null for free tier
    )
    auto_renew: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    trial_end_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # RevenueCat Integration Fields
    revenuecat_subscriber_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        unique=True,
        nullable=True,
        index=True,
    )
    revenuecat_original_app_user_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    revenuecat_entitlements: Mapped[Optional[list]] = mapped_column(
        JSONB,
        nullable=True,
    )
    last_revenuecat_sync: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Payment/Order Fields
    platform: Mapped[Optional[Platform]] = mapped_column(
        SQLEnum(Platform),
        nullable=True,
    )
    product_identifier: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    price_paid: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )
    currency: Mapped[Optional[str]] = mapped_column(
        String(3),
        nullable=True,
    )
    original_purchase_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    latest_purchase_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    store_transaction_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    store_original_transaction_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="subscription",
    )
    history: Mapped[list["SubscriptionHistory"]] = relationship(
        "SubscriptionHistory",
        back_populates="subscription",
        order_by="desc(SubscriptionHistory.created_at)",
    )

    # Indexes
    __table_args__ = (
        Index("idx_subscription_status_expires", "status", "expires_at"),
        Index("idx_subscription_tier_status", "tier", "status"),
    )

    def __repr__(self) -> str:
        return f"<Subscription(user_id={self.user_id}, tier={self.tier}, status={self.status})>"

    @property
    def is_premium(self) -> bool:
        """Check if user has premium subscription."""
        return self.tier in (SubscriptionTier.MONTHLY, SubscriptionTier.ANNUAL)

    @property
    def is_active(self) -> bool:
        """Check if subscription is currently active."""
        return self.status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL)


class SubscriptionHistory(Base):
    """
    Subscription history model.
    
    Tracks all subscription events for audit trail.
    """

    __tablename__ = "subscription_history"

    # Primary Key
    history_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Foreign Keys
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subscriptions.subscription_id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )

    # Event details
    event_type: Mapped[SubscriptionEventType] = mapped_column(
        SQLEnum(SubscriptionEventType),
        nullable=False,
    )
    previous_tier: Mapped[Optional[SubscriptionTier]] = mapped_column(
        SQLEnum(SubscriptionTier),
        nullable=True,
    )
    new_tier: Mapped[SubscriptionTier] = mapped_column(
        SQLEnum(SubscriptionTier),
        nullable=False,
    )
    previous_status: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    new_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    # Payment info
    price_paid: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )
    currency: Mapped[Optional[str]] = mapped_column(
        String(3),
        nullable=True,
    )
    store_transaction_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    # RevenueCat data
    revenuecat_event_data: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
    )

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    subscription: Mapped["Subscription"] = relationship(
        "Subscription",
        back_populates="history",
    )

    # Indexes
    __table_args__ = (
        Index("idx_sub_history_subscription", "subscription_id", "created_at"),
        Index("idx_sub_history_user_event", "user_id", "event_type", "created_at"),
        Index("idx_sub_history_event_date", "event_type", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<SubscriptionHistory(user_id={self.user_id}, event={self.event_type})>"
