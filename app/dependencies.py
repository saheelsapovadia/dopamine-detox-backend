"""
Common Dependencies
===================

Shared dependencies used across the application.
"""

from datetime import datetime, timezone
from typing import Annotated, Optional
import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.db.session import get_db
from app.models.user import User
from app.services.auth_service import AuthService

# Database session dependency
DBSession = Annotated[AsyncSession, Depends(get_db)]

# Security scheme for JWT authentication
security = HTTPBearer(auto_error=False)

# Development test user ID (consistent UUID for testing)
DEV_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
DEV_USER_EMAIL = "dev@test.local"


async def get_or_create_dev_user(db: AsyncSession) -> User:
    """
    Get or create a development test user.
    Only used when DEV_AUTH_DISABLED is True.
    """
    # Try to find existing dev user
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
    
    auth_service = AuthService(db)
    return await auth_service.verify_token(credentials.credentials)


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
    
    auth_service = AuthService(db)
    user = await auth_service.verify_token(credentials.credentials)
    
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
