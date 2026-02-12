"""
Database Session Management
===========================

Provides async database session factory and dependency injection.

Includes ``LazyDB`` — a lightweight wrapper that defers opening a
real DB session until the first call to ``await lazy.get()``.  This
is used by cache-first endpoints so that a pure cache-hit path pays
**zero** DB overhead.
"""

import logging
from typing import AsyncGenerator, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

logger = logging.getLogger(__name__)

# Global engine instance
_engine: AsyncEngine | None = None
_async_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """
    Get or create the async database engine.

    Uses connection pooling with the following configuration:
    - pool_size: 20 connections
    - max_overflow: 40 additional connections
    - pool_recycle: Recycle connections every 5 minutes (matches typical
      Supabase/PgBouncer idle timeouts — prevents stale connections without
      the expensive pool_pre_ping round-trips)
    - pool_use_lifo: Prefer the most-recently-returned connection so it is
      more likely alive and has a warm prepared-statement cache
    - pool_pre_ping DISABLED: On high-latency links (~185 ms/RT) the
      pre-ping check costs ~740 ms (BEGIN + PREPARE + exec + ROLLBACK).
      Stale connections are handled by pool_recycle + LIFO ordering instead.
    """
    global _engine

    if _engine is None:
        if not settings.database_url_async:
            raise ValueError(
                "Database URL not configured. "
                "Please set SUPABASE_DATABASE_URL environment variable."
            )

        _engine = create_async_engine(
            settings.database_url_async,
            echo=settings.is_development,  # Log SQL in development
            pool_size=20,
            max_overflow=40,
            pool_pre_ping=False,
            pool_recycle=300,       # 5 minutes — aggressive recycle replaces pre_ping
            pool_use_lifo=True,     # reuse hot connections first
            pool_timeout=30,
        )

    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create the async session factory."""
    global _async_session_factory
    
    if _async_session_factory is None:
        engine = get_engine()
        _async_session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    
    return _async_session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency that provides a database session.
    
    Usage:
        @app.get("/users")
        async def get_users(db: AsyncSession = Depends(get_db)):
            ...
    
    The session is automatically committed on success or rolled back on error.
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


class LazyDB:
    """
    Lazy database session wrapper.

    No DB connection is opened until ``await lazy.get()`` is called.
    If ``get()`` is never called the cleanup is a no-op — zero overhead.
    """

    def __init__(self) -> None:
        self._session: Optional[AsyncSession] = None

    async def get(self) -> AsyncSession:
        """Return (and lazily create) the underlying session."""
        if self._session is None:
            factory = get_session_factory()
            self._session = factory()
        return self._session

    async def close(self, *, commit: bool = True) -> None:
        """Commit/rollback and close the session if it was ever opened."""
        if self._session is not None:
            try:
                if commit:
                    await self._session.commit()
                else:
                    await self._session.rollback()
            finally:
                await self._session.close()
                self._session = None


async def get_lazy_db() -> AsyncGenerator[LazyDB, None]:
    """
    FastAPI dependency that provides a **lazy** DB session.

    Usage::

        async def my_handler(lazy_db: Annotated[LazyDB, Depends(get_lazy_db)]):
            # Only opens a real DB connection if/when needed:
            db = await lazy_db.get()

    On a pure cache-hit path ``lazy_db.get()`` is never called, so the
    request pays zero DB overhead.
    """
    lazy = LazyDB()
    try:
        yield lazy
    except Exception:
        await lazy.close(commit=False)
        raise
    else:
        await lazy.close(commit=True)


async def init_db() -> None:
    """
    Initialize database connection and warm the connection pool.

    Called on application startup.  Opens several connections up-front
    so the first real requests don't pay TCP + TLS + auth latency.
    """
    engine = get_engine()

    # Warm up to 3 connections in the pool.  Each connection runs a
    # trivial query so the underlying asyncpg connection is fully
    # established (TCP handshake, TLS, auth) and ready to serve.
    warm_target = min(3, engine.pool.size())
    conns = []
    try:
        for _ in range(warm_target):
            conn = await engine.connect()
            await conn.execute(text("SELECT 1"))
            conns.append(conn)
    except Exception as exc:
        logger.warning("Pool warmup partially failed: %s", exc)
    finally:
        for conn in conns:
            await conn.close()

    print(f"✅ Database connection established (pool warmed: {len(conns)} connections)")


async def close_db() -> None:
    """
    Close database connections.
    
    Called on application shutdown to clean up resources.
    """
    global _engine, _async_session_factory
    
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _async_session_factory = None
        print("✅ Database connections closed")
