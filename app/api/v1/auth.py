"""
Authentication API Endpoints
============================

Handles user registration, login, logout, and token refresh.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_tokens_for_user
from app.db.session import get_db
from app.schemas.auth import (
    AuthResponse,
    LoginResponse,
    LogoutResponse,
    RefreshTokenRequest,
    RegisterResponse,
    SubscriptionInfo,
    TokenResponse,
    UserBase,
    UserLogin,
    UserRegister,
)
from app.schemas.common import ErrorResponse
from app.services.auth_service import AuthService

router = APIRouter()


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        409: {"model": ErrorResponse, "description": "Email already registered"},
    },
)
async def register(
    user_data: UserRegister,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Register a new user account.
    
    Creates user with free tier subscription automatically.
    """
    auth_service = AuthService(db)
    
    # Check if email already exists
    existing_user = await auth_service.get_user_by_email(user_data.email)
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "AUTH_001",
                "message": "Email already registered",
            },
        )
    
    # Create user
    user = await auth_service.create_user(user_data)
    
    # Generate tokens
    tokens = create_tokens_for_user(
        user_id=user.user_id,
        email=user.email,
        tier="free",
    )
    
    # Get feature limits
    feature_limits = auth_service.get_feature_limits("free")
    
    return AuthResponse(
        success=True,
        data={
            "user": {
                "user_id": str(user.user_id),
                "email": user.email,
                "full_name": user.full_name,
                "created_at": user.created_at.isoformat(),
            },
            "subscription": {
                "tier": "free",
                "status": "active",
                "feature_limits": feature_limits,
            },
            "tokens": tokens,
        },
        message="Account created successfully",
    )


@router.post(
    "/login",
    response_model=AuthResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Invalid credentials"},
    },
)
async def login(
    credentials: UserLogin,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Authenticate user and return tokens.
    """
    auth_service = AuthService(db)
    
    # Authenticate user
    user = await auth_service.authenticate_user(
        email=credentials.email,
        password=credentials.password,
    )
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "AUTH_001",
                "message": "Invalid credentials",
            },
        )
    
    # Get subscription info
    tier = "free"
    status_val = "active"
    expires_at = None
    
    if user.subscription:
        tier = user.subscription.tier.value
        status_val = user.subscription.status.value
        expires_at = user.subscription.expires_at
    
    # Generate tokens
    tokens = create_tokens_for_user(
        user_id=user.user_id,
        email=user.email,
        tier=tier,
    )
    
    # Get feature limits
    feature_limits = auth_service.get_feature_limits(tier)
    
    return AuthResponse(
        success=True,
        data={
            "user": {
                "user_id": str(user.user_id),
                "email": user.email,
                "full_name": user.full_name,
            },
            "subscription": {
                "tier": tier,
                "status": status_val,
                "expires_at": expires_at.isoformat() if expires_at else None,
                "feature_limits": feature_limits,
            },
            "tokens": tokens,
        },
    )


@router.post(
    "/logout",
    response_model=LogoutResponse,
)
async def logout():
    """
    Logout user (client should discard tokens).
    
    Note: JWT tokens are stateless, so server-side invalidation
    would require a token blacklist (implemented in Phase 4 with Redis).
    """
    return LogoutResponse(
        success=True,
        message="Logged out successfully",
    )


@router.post(
    "/refresh-token",
    response_model=AuthResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Invalid refresh token"},
    },
)
async def refresh_token(
    request: RefreshTokenRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Refresh access token using refresh token.
    """
    auth_service = AuthService(db)
    
    tokens = await auth_service.refresh_tokens(request.refresh_token)
    
    if tokens is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "AUTH_002",
                "message": "Invalid or expired refresh token",
            },
        )
    
    return AuthResponse(
        success=True,
        data={"tokens": tokens},
        message="Tokens refreshed successfully",
    )
