"""
Common Dependencies
===================

Shared dependencies used across the application.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Annotated, Optional
import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.core.security import decode_token
from app.db.session import get_db
from app.models.user import User
from app.models.subscription import Subscription, SubscriptionTier, SubscriptionStatus
from app.services.auth_service import AuthService
from app.services.cache import get_redis

logger = logging.getLogger(__name__)

# Database session dependency
DBSession = Annotated[AsyncSession, Depends(get_db)]

# Security scheme for JWT authentication
security = HTTPBearer(auto_error=False)

# Development test user ID (consistent UUID for testing)
DEV_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
DEV_USER_EMAIL = "dev@test.local"

# Redis cache TTL for authenticated user lookup (seconds)
_USER_AUTH_CACHE_TTL = 300  # 5 minutes


# =============================================================================
# User Auth Cache Helpers
# =============================================================================

def _user_auth_cache_key(user_id: str) -> str:
    """Redis key for cached user auth data."""
    return f"cache:user:auth:{user_id}"


def _serialize_user_for_cache(user: User) -> dict:
    """Serialize a User (+ eager-loaded subscription) to a JSON-safe dict."""
    data: dict = {
        "user_id": str(user.user_id),
        "email": user.email,
        "password_hash": user.password_hash,
        "full_name": user.full_name,
        "last_login": user.last_login.isoformat() if user.last_login else None,
        "timezone": user.timezone,
        "notification_preferences": user.notification_preferences,
        "google_id": user.google_id,
        "avatar_url": user.avatar_url,
        "created_at": user.created_at.isoformat() if getattr(user, "created_at", None) else None,
        "updated_at": user.updated_at.isoformat() if getattr(user, "updated_at", None) else None,
        "subscription": None,
    }
    sub = user.subscription
    if sub:
        data["subscription"] = {
            "subscription_id": str(sub.subscription_id),
            "user_id": str(sub.user_id),
            "tier": sub.tier.value if isinstance(sub.tier, SubscriptionTier) else str(sub.tier),
            "status": sub.status.value if isinstance(sub.status, SubscriptionStatus) else str(sub.status),
            "started_at": sub.started_at.isoformat() if sub.started_at else None,
            "expires_at": sub.expires_at.isoformat() if sub.expires_at else None,
            "auto_renew": sub.auto_renew,
            "trial_end_date": sub.trial_end_date.isoformat() if sub.trial_end_date else None,
            "cancelled_at": sub.cancelled_at.isoformat() if sub.cancelled_at else None,
        }
    return data


def _parse_dt(value: str | None) -> datetime | None:
    """Parse an ISO datetime string, returning None on missing/invalid input."""
    if not value:
        return None
    return datetime.fromisoformat(value)


def _build_user_from_cache(data: dict) -> User:
    """
    Reconstruct a *transient* (session-free) User from a cached dict.

    The returned object is NOT attached to any SQLAlchemy session, which is
    fine because the ``CurrentUser`` dependency consumers only read attributes.
    """
    user = User(
        user_id=uuid.UUID(data["user_id"]),
        email=data["email"],
        password_hash=data.get("password_hash"),
        full_name=data.get("full_name"),
        last_login=_parse_dt(data.get("last_login")),
        timezone=data.get("timezone"),
        notification_preferences=data.get("notification_preferences"),
        google_id=data.get("google_id"),
        avatar_url=data.get("avatar_url"),
        created_at=_parse_dt(data.get("created_at")) or datetime.now(timezone.utc),
        updated_at=_parse_dt(data.get("updated_at")) or datetime.now(timezone.utc),
    )

    sub_data = data.get("subscription")
    if sub_data:
        sub = Subscription(
            subscription_id=uuid.UUID(sub_data["subscription_id"]),
            user_id=uuid.UUID(sub_data["user_id"]),
            tier=SubscriptionTier(sub_data["tier"]),
            status=SubscriptionStatus(sub_data["status"]),
            started_at=_parse_dt(sub_data.get("started_at")) or datetime.now(timezone.utc),
            expires_at=_parse_dt(sub_data.get("expires_at")),
            auto_renew=sub_data.get("auto_renew", False),
            trial_end_date=_parse_dt(sub_data.get("trial_end_date")),
            cancelled_at=_parse_dt(sub_data.get("cancelled_at")),
        )
        user.subscription = sub

    return user


async def _get_cached_user(user_id: uuid.UUID) -> User | None:
    """Return the cached User object, or ``None`` on miss / Redis failure."""
    try:
        client = await get_redis()
        raw = await client.get(_user_auth_cache_key(str(user_id)))
        if raw is None:
            return None
        return _build_user_from_cache(json.loads(raw))
    except Exception:
        return None


async def _cache_user(user: User) -> None:
    """Best-effort cache of a DB-loaded User into Redis."""
    try:
        client = await get_redis()
        data = _serialize_user_for_cache(user)
        await client.setex(
            _user_auth_cache_key(str(user.user_id)),
            _USER_AUTH_CACHE_TTL,
            json.dumps(data, default=str),
        )
    except Exception:
        pass  # non-critical; next request will just hit DB


# =============================================================================
# User resolution
# =============================================================================

async def get_or_create_dev_user(db: AsyncSession) -> User:
    """
    Get or create a development test user.
    Only used when DEV_AUTH_DISABLED is True.

    Checks Redis cache first to avoid hitting PostgreSQL on every request.
    """
    # Fast path — return from cache
    cached = await _get_cached_user(DEV_USER_ID)
    if cached is not None:
        return cached

    # Cache miss — query DB
    result = await db.execute(
        select(User).where(User.user_id == DEV_USER_ID)
    )
    user = result.scalar_one_or_none()
    
    if user is None:
        # Create dev user if doesn't exist
        user = User(
            user_id=DEV_USER_ID,
            email=DEV_USER_EMAIL,
            full_name="Development User",
            timezone="UTC",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    # Populate cache for subsequent requests
    await _cache_user(user)
    return user


async def _resolve_user_from_token(
    credentials: HTTPAuthorizationCredentials,
    db: AsyncSession,
) -> User | None:
    """
    Decode the JWT, then return the User from Redis cache or DB.

    Separating JWT decode from the DB lookup lets us skip PostgreSQL
    entirely when the user is already cached in Redis.
    """
    payload = decode_token(credentials.credentials)
    if payload is None or payload.get("type") != "access":
        return None

    user_id_str = payload.get("sub")
    if user_id_str is None:
        return None

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        return None

    # Fast path — Redis cache hit
    cached = await _get_cached_user(user_id)
    if cached is not None:
        return cached

    # Cache miss — fall back to DB
    auth_service = AuthService(db)
    user = await auth_service.get_user_by_id(user_id)
    if user is not None:
        await _cache_user(user)
    return user


async def get_current_user_optional(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: DBSession,
) -> Optional[User]:
    """
    Get current user if authenticated, None otherwise.
    
    Use this for endpoints that work with or without authentication.
    In development with DEV_AUTH_DISABLED=True, returns the dev user.
    """
    # If auth is disabled in development, return dev user
    if settings.auth_disabled:
        return await get_or_create_dev_user(db)
    
    if credentials is None:
        return None
    
    return await _resolve_user_from_token(credentials, db)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: DBSession,
) -> User:
    """
    Get current authenticated user.
    
    Raises 401 if not authenticated or token is invalid.
    In development with DEV_AUTH_DISABLED=True, returns the dev user.
    """
    # If auth is disabled in development, return dev user
    if settings.auth_disabled:
        return await get_or_create_dev_user(db)
    
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "AUTH_002",
                "message": "Not authenticated",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = await _resolve_user_from_token(credentials, db)
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "AUTH_002",
                "message": "Invalid or expired token",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user


# Type alias for authenticated user dependency
CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentUserOptional = Annotated[Optional[User], Depends(get_current_user_optional)]
