"""
Authentication Service
======================

Business logic for user authentication, registration, and token management.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
import uuid

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import (
    create_tokens_for_user,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.models.subscription import Subscription, SubscriptionTier, SubscriptionStatus
from app.schemas.auth import UserRegister

logger = logging.getLogger(__name__)


class AuthService:
    """Service for authentication operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email address."""
        stmt = select(User).where(User.email == email)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        """Get user by ID."""
        stmt = select(User).where(User.user_id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create_user(self, user_data: UserRegister) -> User:
        """
        Create a new user with free subscription.
        
        Args:
            user_data: Registration data
            
        Returns:
            Created user object
        """
        # Create user
        user = User(
            email=user_data.email,
            password_hash=hash_password(user_data.password),
            full_name=user_data.full_name,
            timezone=user_data.timezone,
        )
        self.db.add(user)
        await self.db.flush()  # Get user_id

        # Create free subscription
        subscription = Subscription(
            user_id=user.user_id,
            tier=SubscriptionTier.FREE,
            status=SubscriptionStatus.ACTIVE,
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(subscription)

        await self.db.flush()
        
        return user

    async def authenticate_user(
        self,
        email: str,
        password: str,
    ) -> Optional[User]:
        """
        Authenticate user by email and password.
        
        Args:
            email: User's email
            password: Plain text password
            
        Returns:
            User if authentication successful, None otherwise
        """
        user = await self.get_user_by_email(email)
        
        if user is None:
            return None
        
        if user.password_hash is None:
            # OAuth user without password
            return None
        
        if not verify_password(password, user.password_hash):
            return None
        
        # Update last login
        user.last_login = datetime.now(timezone.utc)
        
        return user

    async def verify_token(self, token: str) -> Optional[User]:
        """
        Verify JWT token and return associated user.
        
        Args:
            token: JWT token string
            
        Returns:
            User if token is valid, None otherwise
        """
        payload = decode_token(token)
        
        if payload is None:
            return None
        
        # Check token type
        if payload.get("type") != "access":
            return None
        
        # Get user ID from token
        user_id_str = payload.get("sub")
        if user_id_str is None:
            return None
        
        try:
            user_id = uuid.UUID(user_id_str)
        except ValueError:
            return None
        
        return await self.get_user_by_id(user_id)

    async def refresh_tokens(self, refresh_token: str) -> Optional[dict]:
        """
        Generate new tokens from a refresh token.
        
        Args:
            refresh_token: Valid refresh token
            
        Returns:
            New tokens if refresh token is valid, None otherwise
        """
        payload = decode_token(refresh_token)
        
        if payload is None:
            return None
        
        # Check token type
        if payload.get("type") != "refresh":
            return None
        
        # Get user
        user_id_str = payload.get("sub")
        if user_id_str is None:
            return None
        
        try:
            user_id = uuid.UUID(user_id_str)
        except ValueError:
            return None
        
        user = await self.get_user_by_id(user_id)
        if user is None:
            return None
        
        # Get subscription tier
        tier = "free"
        if user.subscription:
            tier = user.subscription.tier.value
        
        return create_tokens_for_user(
            user_id=user.user_id,
            email=user.email,
            tier=tier,
        )

    async def create_oauth_user(
        self,
        email: str,
        full_name: Optional[str],
        google_id: str,
        avatar_url: Optional[str] = None,
    ) -> User:
        """
        Create or get user from OAuth login.
        
        Args:
            email: User's email from OAuth
            full_name: User's name from OAuth
            google_id: Google's unique user ID
            avatar_url: Profile picture URL
            
        Returns:
            User object
        """
        # Check if user exists
        user = await self.get_user_by_email(email)
        
        if user is not None:
            # Update Google ID if not set
            if user.google_id is None:
                user.google_id = google_id
                user.avatar_url = avatar_url
            user.last_login = datetime.now(timezone.utc)
            return user
        
        # Create new user
        user = User(
            email=email,
            full_name=full_name,
            google_id=google_id,
            avatar_url=avatar_url,
        )
        self.db.add(user)
        await self.db.flush()

        # Create free subscription
        subscription = Subscription(
            user_id=user.user_id,
            tier=SubscriptionTier.FREE,
            status=SubscriptionStatus.ACTIVE,
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(subscription)

        await self.db.flush()

        # Refresh to populate the selectin-loaded 'subscription' relationship
        # so callers can access user.subscription without triggering a
        # synchronous lazy load (which would fail in async context).
        await self.db.refresh(user, ["subscription"])

        return user

    async def verify_google_id_token(self, token: str) -> dict:
        """
        Verify a Google ID token and return the decoded user info.

        Uses google-auth library to cryptographically verify the token
        signature, expiry, issuer, and audience against configured client IDs.

        The verification is CPU-bound / synchronous, so it is offloaded
        to a thread to avoid blocking the event loop.

        Args:
            token: Raw Google ID token string from client.

        Returns:
            Dict with keys: sub, email, email_verified, name, picture, etc.

        Raises:
            ValueError: If the token is invalid, expired, or has a
                        wrong audience / issuer.
        """
        client_ids = settings.google_oauth_client_ids

        def _verify() -> dict:
            """Try verification against each configured client ID."""
            request = google_requests.Request()
            last_error: Exception | None = None

            for client_id in client_ids:
                try:
                    idinfo = google_id_token.verify_oauth2_token(
                        token, request, audience=client_id,
                        clock_skew_in_seconds=5,
                    )
                    # Validate issuer
                    if idinfo.get("iss") not in (
                        "accounts.google.com",
                        "https://accounts.google.com",
                    ):
                        raise ValueError("Invalid token issuer")
                    return idinfo
                except ValueError as exc:
                    last_error = exc
                    continue

            # If no client IDs matched or none are configured, try without
            # audience check as a last resort (still verifies signature).
            if not client_ids:
                try:
                    idinfo = google_id_token.verify_oauth2_token(
                        token, request, audience=None,
                        clock_skew_in_seconds=5,
                    )
                    if idinfo.get("iss") not in (
                        "accounts.google.com",
                        "https://accounts.google.com",
                    ):
                        raise ValueError("Invalid token issuer")
                    logger.warning(
                        "Google token verified without audience check — "
                        "configure GOOGLE_OAUTH_CLIENT_ID for production safety"
                    )
                    return idinfo
                except ValueError as exc:
                    last_error = exc

            raise last_error or ValueError("Google token verification failed")

        return await asyncio.to_thread(_verify)

    def get_feature_limits(self, tier: str) -> dict:
        """Get feature limits for a subscription tier."""
        limits = {
            "free": {
                "journals_per_month": 1,
                "ai_insights": False,
                "ai_analysis": False,
                "voice_transcription": False,
                "progress_reports": False,
                "unlimited_tasks": True,
                "ads_enabled": True,
                "advanced_analytics": False,
                "priority_support": False,
            },
            "monthly": {
                "journals_per_month": -1,  # Unlimited
                "ai_insights": True,
                "ai_analysis": True,
                "voice_transcription": True,
                "progress_reports": True,
                "unlimited_tasks": True,
                "ads_enabled": False,
                "advanced_analytics": True,
                "priority_support": False,
            },
            "annual": {
                "journals_per_month": -1,  # Unlimited
                "ai_insights": True,
                "ai_analysis": True,
                "voice_transcription": True,
                "progress_reports": True,
                "unlimited_tasks": True,
                "ads_enabled": False,
                "advanced_analytics": True,
                "priority_support": True,
            },
        }
        return limits.get(tier, limits["free"])
