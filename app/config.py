"""
Application Configuration
=========================

Centralized configuration using Pydantic Settings.
Loads from environment variables with validation.
"""

from functools import lru_cache
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Environment
    ENVIRONMENT: str = Field(default="development")

    # Server
    PORT: int = Field(default=8000, description="Port to bind to (Render injects this)")
    
    # Development Settings
    DEV_AUTH_DISABLED: bool = Field(
        default=False,
        description="Disable authentication for local development/testing"
    )

    # Database - Supabase
    SUPABASE_URL: str = Field(default="")
    SUPABASE_ANON_KEY: str = Field(default="")
    SUPABASE_SERVICE_ROLE_KEY: str = Field(default="")
    SUPABASE_DATABASE_URL: str = Field(default="")

    # Redis
    REDIS_URL: str = Field(default="redis://localhost:6379/0")

    # Azure Blob Storage
    AZURE_STORAGE_CONNECTION_STRING: str = Field(default="")
    AZURE_STORAGE_ACCOUNT_NAME: str = Field(default="")
    AZURE_STORAGE_ACCOUNT_KEY: str = Field(default="")
    AZURE_STORAGE_CONTAINER: str = Field(default="dopamine-detox-dev")

    # Google Cloud
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = Field(default=None)
    GOOGLE_CLOUD_PROJECT: Optional[str] = Field(default=None)
    GOOGLE_GEMINI_API_KEY: str = Field(default="")
    GEMINI_MODEL: str = Field(default="gemini-1.5-flash")

    # Deepgram (real-time speech-to-text)
    DEEPGRAM_API_KEY: str = Field(default="")

    # JWT Authentication
    JWT_SECRET: str = Field(default="change-this-secret-in-production")
    JWT_ALGORITHM: str = Field(default="HS256")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=1440)  # 24 hours
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=30)

    # Google OAuth
    GOOGLE_OAUTH_CLIENT_ID: Optional[str] = Field(default=None)
    GOOGLE_OAUTH_CLIENT_SECRET: Optional[str] = Field(default=None)

    # RevenueCat
    REVENUECAT_API_KEY: str = Field(default="")
    REVENUECAT_WEBHOOK_SECRET: str = Field(default="")
    REVENUECAT_PUBLIC_KEY: str = Field(default="")

    # App Configuration
    API_BASE_URL: str = Field(default="http://localhost:8000")
    FRONTEND_URL: str = Field(default="http://localhost:3000")
    ALLOWED_ORIGINS: str = Field(default="http://localhost:3000,http://localhost:8000")

    # File Upload
    MAX_VOICE_UPLOAD_SIZE_MB: int = Field(default=10)
    ALLOWED_AUDIO_FORMATS: str = Field(default="mp3,wav,m4a,ogg")

    @property
    def allowed_origins_list(self) -> List[str]:
        """Parse ALLOWED_ORIGINS into a list."""
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]

    @property
    def allowed_audio_formats_list(self) -> List[str]:
        """Parse ALLOWED_AUDIO_FORMATS into a list."""
        return [fmt.strip() for fmt in self.ALLOWED_AUDIO_FORMATS.split(",")]

    @property
    def database_url_async(self) -> str:
        """Convert database URL to async format for asyncpg."""
        if self.SUPABASE_DATABASE_URL:
            return self.SUPABASE_DATABASE_URL.replace(
                "postgresql://", "postgresql+asyncpg://"
            )
        return ""

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.ENVIRONMENT.lower() == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.ENVIRONMENT.lower() == "development"

    @property
    def auth_disabled(self) -> bool:
        """Check if auth is disabled (only allowed in development)."""
        return self.is_development and self.DEV_AUTH_DISABLED

    @field_validator("JWT_SECRET")
    @classmethod
    def validate_jwt_secret(cls, v: str) -> str:
        """Ensure JWT secret is sufficiently long."""
        if len(v) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters long")
        return v


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.
    
    Uses lru_cache to ensure settings are loaded only once.
    """
    return Settings()


# Export a default settings instance
settings = get_settings()
