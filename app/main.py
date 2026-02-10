"""
Dopamine Detox API - Main Application
=====================================

FastAPI application entry point with middleware configuration
and route registration.
"""

import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import newrelic.agent
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.db.session import init_db, close_db
from app.services.cache import init_redis, close_redis
from app.core.errors import setup_exception_handlers


# =============================================================================
# New Relic Transaction Enrichment Middleware
# =============================================================================

class NewRelicTransactionMiddleware(BaseHTTPMiddleware):
    """
    Lightweight middleware that enriches every New Relic transaction with
    custom attributes for better filtering, alerting, and dashboarding.
    
    Captures: response status, latency, HTTP method, route pattern, and
    user ID (when authenticated).
    """

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()

        response = await call_next(request)

        duration_ms = (time.perf_counter() - start) * 1000

        # Add custom attributes to the current New Relic transaction
        txn = newrelic.agent.current_transaction()
        if txn:
            # Route pattern (e.g. "/api/v1/tasks/{task_id}") for grouping
            route = request.scope.get("route")
            route_path = route.path if route else request.url.path

            newrelic.agent.add_custom_attributes([
                ("http.method", request.method),
                ("http.route", route_path),
                ("http.status_code", response.status_code),
                ("http.duration_ms", round(duration_ms, 2)),
                ("http.client_ip", request.client.host if request.client else "unknown"),
            ])

            # Attach user_id if present (set by auth dependency)
            user_id = getattr(request.state, "user_id", None)
            if user_id:
                newrelic.agent.add_custom_attribute("enduser.id", str(user_id))

        return response


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.
    
    Handles startup and shutdown events for:
    - Database connection
    - Redis connection
    """
    # Startup
    print("🚀 Starting Dopamine Detox API...")
    
    # Warn if auth is disabled
    if settings.auth_disabled:
        print("⚠️  WARNING: Authentication is DISABLED (DEV_AUTH_DISABLED=true)")
        print("⚠️  All requests will use the development test user.")
        print("⚠️  DO NOT use this setting in production!")
    
    # Initialize database
    try:
        await init_db()
    except Exception as e:
        print(f"⚠️ Database connection failed: {e}")
        # Continue startup even if DB fails (for health checks)
    
    # Initialize Redis
    try:
        await init_redis()
    except Exception as e:
        print(f"⚠️ Redis connection failed: {e}")
    
    yield
    
    # Shutdown
    print("🛑 Shutting down Dopamine Detox API...")
    await close_db()
    await close_redis()


# Create FastAPI application
app = FastAPI(
    title="Dopamine Detox API",
    description="""
## Dopamine Detox and Mindfulness Application Backend

A comprehensive API for habit tracking, journaling, and mindful daily planning.

### Features
- **Authentication**: Email/password and Google OAuth
- **Task Management**: Voice-enabled daily planning with AI task extraction
- **Journaling**: Text and voice entries with AI emotion analysis
- **Subscription**: RevenueCat integration for premium features

### Rate Limits
- Authentication: 5 requests/minute
- Creation endpoints: 30 requests/minute
- Read endpoints: 100 requests/minute
- Voice uploads: 10 requests/minute

### File Limits
- Voice recordings: Max 10MB
- Supported formats: MP3, WAV, M4A, OGG
    """,
    version="1.0.0",
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
    openapi_url="/openapi.json" if settings.is_development else None,
    lifespan=lifespan,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Permission denied or feature locked"},
        404: {"description": "Resource not found"},
        409: {"description": "Resource conflict"},
        422: {"description": "Validation error"},
        429: {"description": "Rate limit exceeded"},
        500: {"description": "Internal server error"},
    },
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# New Relic transaction enrichment (adds custom attrs to every transaction)
app.add_middleware(NewRelicTransactionMiddleware)

# Setup exception handlers
setup_exception_handlers(app)


# =============================================================================
# Health Check Endpoints
# =============================================================================

@app.get("/health", tags=["Health"])
async def health_check() -> dict:
    """
    Health check endpoint.
    
    Returns the current status of the API and its dependencies.
    """
    return {
        "status": "healthy",
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT,
    }


@app.get("/", tags=["Health"])
async def root() -> dict:
    """Root endpoint with API information."""
    return {
        "name": "Dopamine Detox API",
        "version": "1.0.0",
        "docs": "/docs" if settings.is_development else "Disabled in production",
    }


# =============================================================================
# API Routes
# =============================================================================

# Phase 3: Authentication
from app.api.v1 import auth
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])

# Phase 5: Profile
from app.api.v1 import profile
app.include_router(profile.router, prefix="/api/v1/profile", tags=["Profile"])

# Phase 6: Tasks
from app.api.v1 import tasks
app.include_router(tasks.router, prefix="/api/v1/tasks", tags=["Tasks"])

# Phase 7: Journal
from app.api.v1 import journal
app.include_router(journal.router, prefix="/api/v1/journal", tags=["Journal"])

# Phase 8: Subscription
from app.api.v1 import subscription, webhooks, features
app.include_router(subscription.router, prefix="/api/v1/subscription", tags=["Subscription"])
app.include_router(webhooks.router, prefix="/api/v1/webhooks", tags=["Webhooks"])
app.include_router(features.router, prefix="/api/v1/features", tags=["Features"])

# Phase 15: User-scoped Tasks (HomeScreen v2 API)
from app.api.v1 import user_tasks
app.include_router(user_tasks.router, prefix="/api/v1/users", tags=["User Tasks"])
