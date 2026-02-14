"""
Authentication Schemas
======================

Pydantic schemas for authentication endpoints.
"""

from datetime import datetime
from typing import Any, Optional
import uuid

from pydantic import BaseModel, EmailStr, Field, field_validator


class UserRegister(BaseModel):
    """Request schema for user registration."""
    
    email: EmailStr
    password: str = Field(min_length=8, max_length=100)
    full_name: Optional[str] = Field(None, max_length=255)
    timezone: Optional[str] = Field(default="UTC", max_length=50)
    
    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password strength."""
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one number")
        return v


class UserLogin(BaseModel):
    """Request schema for user login."""
    
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Response schema for tokens."""
    
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class RefreshTokenRequest(BaseModel):
    """Request schema for token refresh."""
    
    refresh_token: str


class UserBase(BaseModel):
    """Base user schema."""
    
    user_id: uuid.UUID
    email: EmailStr
    full_name: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class SubscriptionInfo(BaseModel):
    """Subscription info in auth response."""
    
    tier: str
    status: str
    expires_at: Optional[datetime] = None
    feature_limits: Optional[dict[str, Any]] = None
    
    class Config:
        from_attributes = True


class AuthResponse(BaseModel):
    """Response schema for authentication endpoints."""
    
    success: bool = True
    data: dict[str, Any]
    message: Optional[str] = None


class RegisterResponse(BaseModel):
    """Response schema for user registration."""
    
    user: UserBase
    subscription: SubscriptionInfo
    tokens: TokenResponse


class LoginResponse(BaseModel):
    """Response schema for user login."""
    
    user: UserBase
    subscription: SubscriptionInfo
    tokens: TokenResponse


class LogoutResponse(BaseModel):
    """Response schema for logout."""
    
    success: bool = True
    message: str = "Logged out successfully"


class GoogleLoginRequest(BaseModel):
    """Request schema for Google OAuth login."""
    
    id_token: str = Field(
        ...,
        min_length=1,
        description="Google ID token obtained from client-side Google Sign-In",
    )


class PasswordResetRequest(BaseModel):
    """Request schema for password reset."""
    
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Request schema for password reset confirmation."""
    
    token: str
    new_password: str = Field(min_length=8, max_length=100)
    
    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password strength."""
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one number")
        return v
