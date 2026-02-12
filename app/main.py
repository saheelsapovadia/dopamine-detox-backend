"""
Dopamine Detox API - Main Application
=====================================

FastAPI application entry point with middleware configuration
and route registration.
"""

import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import newrelic.agent

# Configure logging for the application (root logger defaults to WARNING)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.session import init_db, close_db
from app.services.cache import init_redis, close_redis
from app.services.sync_worker import TaskSyncWorker
from app.core.errors import setup_exception_handlers


# =============================================================================
# New Relic Transaction Enrichment Middleware (Raw ASGI)
# =============================================================================

class NewRelicTransactionMiddleware:
    """
    Raw ASGI middleware that enriches every New Relic transaction with
    custom attributes for better filtering, alerting, and dashboarding.

    Uses raw ASGI instead of BaseHTTPMiddleware to preserve the async
    context chain.  BaseHTTPMiddleware's ``call_next()`` spawns the
    route handler in a separate task, which breaks New Relic's
    contextvars-based span propagation — causing Redis, DB, and other
    child spans to disappear from traces.

    Captures: response status, latency, HTTP method, route pattern, and
    user ID (when authenticated).
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status_code = 500  # default until we capture the real one

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = (time.perf_counter() - start) * 1000

            txn = newrelic.agent.current_transaction()
            if txn:
                # Route pattern (e.g. "/api/v1/tasks/{task_id}") for grouping
                route = scope.get("route")
                route_path = route.path if route else scope.get("path", "unknown")

                client = scope.get("client")
                client_ip = client[0] if client else "unknown"

                newrelic.agent.add_custom_attributes([
                    ("http.method", scope.get("method", "")),
                    ("http.route", route_path),
                    ("http.status_code", status_code),
                    ("http.duration_ms", round(duration_ms, 2)),
                    ("http.client_ip", client_ip),
                    ("environment", settings.ENVIRONMENT),
                ])

                # Attach user_id if present (set by auth dependency)
                state = scope.get("state")
                user_id = getattr(state, "user_id", None) if state else None
                if user_id:
                    newrelic.agent.add_custom_attribute("enduser.id", str(user_id))


_sync_worker: TaskSyncWorker | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.
    
    Handles startup and shutdown events for:
    - Database connection
    - Redis connection
    - Task sync background worker (write-behind to PostgreSQL)
    """
    global _sync_worker

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
    
    # Start task sync worker (write-behind cache → PostgreSQL)
    # DISABLED: Upstash Redis free-tier request limit (500k) exhausted;
    #           the worker loop burns requests on every iteration.
    # try:
    #     _sync_worker = TaskSyncWorker()
    #     await _sync_worker.start()
    # except Exception as e:
    #     print(f"⚠️ Task sync worker failed to start: {e}")
    #     _sync_worker = None
    
    yield
    
    # Shutdown
    print("🛑 Shutting down Dopamine Detox API...")
    if _sync_worker is not None:
        await _sync_worker.stop()
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

# Real-time Speech-to-Text (WebSocket)
from app.api.v1 import journal_stream
app.include_router(journal_stream.router, prefix="/api/v1/journal", tags=["Journal Stream"])
