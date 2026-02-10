"""
Database Session Management
===========================

Provides async database session factory and dependency injection.
"""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

# Global engine instance
_engine: AsyncEngine | None = None
_async_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """
    Get or create the async database engine.
    
    Uses connection pooling with the following configuration:
    - pool_size: 20 connections
    - max_overflow: 40 additional connections
    - pool_pre_ping: Check connection health before use
    - pool_recycle: Recycle connections after 1 hour
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
            pool_pre_ping=True,
            pool_recycle=3600,  # 1 hour
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


async def init_db() -> None:
    """
    Initialize database connection.
    
    Called on application startup to verify database connectivity.
    """
    engine = get_engine()
    
    # Test connection
    async with engine.begin() as conn:
        await conn.run_sync(lambda _: None)
    
    print("✅ Database connection established")


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
