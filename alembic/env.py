"""
Alembic Environment Configuration
=================================

Configures Alembic to work with our async SQLAlchemy setup.
"""

import sys
from pathlib import Path

# Add project root to Python path so 'app' module can be found
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import json
import time
from logging.config import fileConfig
from urllib.parse import urlparse

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Load application configuration
from app.config import settings
from app.db.base import Base

# #region agent log
def _debug_log(location, message, data=None):
    log_path = Path(__file__).resolve().parent.parent / ".cursor" / "debug.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {"timestamp": int(time.time()*1000), "location": location, "message": message, "data": data or {}, "sessionId": "debug-session", "hypothesisId": "A"}
    with open(log_path, "a") as f:
        f.write(json.dumps(entry) + "\n")
# #endregion

# Import all models to ensure they are registered with metadata
from app.models.user import User
from app.models.subscription import Subscription, SubscriptionHistory
from app.models.journal import JournalEntry, JournalInsight, DailyMetric
from app.models.task import Task, DailyPlan

# Alembic Config object
config = context.config

# Setup logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Model metadata for autogenerate
target_metadata = Base.metadata


def get_database_url() -> str:
    """Get the async database URL from settings."""
    # #region agent log
    url = settings.database_url_async
    parsed = urlparse(url)
    sanitized_url = f"{parsed.scheme}://{parsed.username}:***@{parsed.hostname}:{parsed.port}{parsed.path}"
    _debug_log("env.py:get_database_url", "Database URL resolved", {"sanitized_url": sanitized_url, "host": parsed.hostname, "port": parsed.port, "database": parsed.path, "user": parsed.username})
    # #endregion
    return settings.database_url_async


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine,
    though an Engine is also acceptable here. By skipping the Engine
    creation we don't even need a DBAPI to be available.
    """
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with a connection."""
    # #region agent log
    _debug_log("env.py:do_run_migrations", "Configuring migration context", {"dialect": connection.dialect.name, "driver": connection.dialect.driver})
    # #endregion
    
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        # #region agent log
        _debug_log("env.py:do_run_migrations", "Running migrations within transaction")
        # #endregion
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Run migrations in async mode.
    
    Creates an async engine and runs migrations.
    """
    # #region agent log
    _debug_log("env.py:run_async_migrations", "Starting async migrations")
    # #endregion
    
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_database_url()
    
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    # #region agent log
    _debug_log("env.py:run_async_migrations", "Engine created, connecting to database", {"engine_url": str(connectable.url).replace(str(connectable.url.password or ""), "***")})
    # #endregion
    
    async with connectable.connect() as connection:
        # #region agent log
        _debug_log("env.py:run_async_migrations", "Connection established, running migrations")
        # #endregion
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()
    
    # #region agent log
    _debug_log("env.py:run_async_migrations", "Migrations completed successfully")
    # #endregion


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.

    Creates an async Engine and associates a connection with the context.
    """
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
