"""
Redis Cache Service
===================

Redis caching layer for application data with connection management,
cache operations, and invalidation utilities.
"""

import json
from datetime import timedelta
from typing import Any, Optional, TypeVar, Union

import redis.asyncio as redis
from redis.asyncio import Redis

from app.config import settings

T = TypeVar("T")

# Global Redis client instance
_redis_client: Optional[Redis] = None


async def init_redis() -> Redis:
    """
    Initialize Redis connection pool and pre-warm a connection.
    
    Returns:
        Redis client instance
    """
    global _redis_client
    
    if _redis_client is None:
        _redis_client = await redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=50,
            socket_keepalive=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30,
        )
        # Pre-warm: force a real connection so the first request
        # doesn't pay the TCP + TLS handshake cost.
        await _redis_client.ping()
        print("✅ Redis connection established")
    
    return _redis_client


async def get_redis() -> Redis:
    """Get Redis client, initializing if necessary."""
    global _redis_client
    
    if _redis_client is None:
        return await init_redis()
    
    return _redis_client


async def close_redis() -> None:
    """Close Redis connection."""
    global _redis_client
    
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None
        print("✅ Redis connection closed")


class CacheManager:
    """
    Redis cache manager with common operations.
    
    Key naming convention:
        cache:{module}:{resource}:{identifier}:{optional_params}
    
    TTL Guidelines:
        - User Sessions: 24 hours
        - Profile Data: 5 minutes (300s)
        - Subscription Status: 1 hour (3600s)
        - Today's Tasks: 5 minutes (300s)
        - Stories/Insights: 15 minutes (900s)
        - Journal Entries List: 15 minutes (900s)
        - Individual Journal Entry: 30 minutes (1800s)
        - Onboarding Progress: 1 hour (3600s)
    """
    
    # Default TTLs in seconds
    TTL_SHORT = 300  # 5 minutes
    TTL_MEDIUM = 900  # 15 minutes
    TTL_LONG = 1800  # 30 minutes
    TTL_HOUR = 3600  # 1 hour
    TTL_DAY = 86400  # 24 hours
    
    @staticmethod
    async def get(key: str) -> Optional[Any]:
        """
        Get value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value if exists and valid, None otherwise
        """
        try:
            client = await get_redis()
            value = await client.get(key)
            
            if value is None:
                return None
            
            return json.loads(value)
        except Exception as e:
            print(f"Cache get error for key {key}: {e}")
            return None
    
    @staticmethod
    async def set(
        key: str,
        value: Any,
        ttl: int = TTL_SHORT,
    ) -> bool:
        """
        Set value in cache with TTL.
        
        Args:
            key: Cache key
            value: Value to cache (will be JSON serialized)
            ttl: Time to live in seconds (default 5 minutes)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            client = await get_redis()
            serialized = json.dumps(value, default=str)
            await client.setex(key, ttl, serialized)
            return True
        except Exception as e:
            print(f"Cache set error for key {key}: {e}")
            return False
    
    @staticmethod
    async def delete(key: str) -> bool:
        """
        Delete key from cache.
        
        Args:
            key: Cache key to delete
            
        Returns:
            True if key was deleted, False otherwise
        """
        try:
            client = await get_redis()
            result = await client.delete(key)
            return result > 0
        except Exception as e:
            print(f"Cache delete error for key {key}: {e}")
            return False
    
    @staticmethod
    async def delete_pattern(pattern: str) -> int:
        """
        Delete all keys matching a pattern.
        
        Args:
            pattern: Pattern with wildcards (e.g., "cache:user:*")
            
        Returns:
            Number of keys deleted
        """
        try:
            client = await get_redis()
            keys = []
            
            async for key in client.scan_iter(match=pattern):
                keys.append(key)
            
            if keys:
                return await client.delete(*keys)
            return 0
        except Exception as e:
            print(f"Cache delete pattern error for {pattern}: {e}")
            return 0
    
    @staticmethod
    async def exists(key: str) -> bool:
        """
        Check if key exists in cache.
        
        Args:
            key: Cache key
            
        Returns:
            True if key exists, False otherwise
        """
        try:
            client = await get_redis()
            return await client.exists(key) > 0
        except Exception as e:
            print(f"Cache exists error for key {key}: {e}")
            return False
    
    @staticmethod
    async def get_ttl(key: str) -> int:
        """
        Get remaining TTL for a key.
        
        Args:
            key: Cache key
            
        Returns:
            TTL in seconds, -2 if key doesn't exist, -1 if no TTL
        """
        try:
            client = await get_redis()
            return await client.ttl(key)
        except Exception as e:
            print(f"Cache TTL error for key {key}: {e}")
            return -2
    
    @staticmethod
    async def increment(key: str, amount: int = 1) -> Optional[int]:
        """
        Increment a counter.
        
        Args:
            key: Cache key
            amount: Amount to increment by
            
        Returns:
            New value after increment, None on error
        """
        try:
            client = await get_redis()
            return await client.incrby(key, amount)
        except Exception as e:
            print(f"Cache increment error for key {key}: {e}")
            return None
    
    @staticmethod
    async def set_with_check(
        key: str,
        value: Any,
        ttl: int = TTL_SHORT,
    ) -> bool:
        """
        Set value only if key doesn't exist (NX).
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds
            
        Returns:
            True if set (key didn't exist), False otherwise
        """
        try:
            client = await get_redis()
            serialized = json.dumps(value, default=str)
            result = await client.set(key, serialized, ex=ttl, nx=True)
            return result is True
        except Exception as e:
            print(f"Cache set_with_check error for key {key}: {e}")
            return False


# =============================================================================
# Cache Key Builders
# =============================================================================

class CacheKeys:
    """Cache key builders for consistent naming."""
    
    @staticmethod
    def user_auth(user_id: str) -> str:
        """Cached user auth lookup (User + Subscription from dependencies)."""
        return f"cache:user:auth:{user_id}"

    @staticmethod
    def profile(user_id: str) -> str:
        """User profile cache key."""
        return f"cache:profile:{user_id}"
    
    @staticmethod
    def subscription(user_id: str) -> str:
        """User subscription cache key."""
        return f"cache:subscription:{user_id}"
    
    @staticmethod
    def subscription_status(user_id: str) -> str:
        """User subscription status cache key."""
        return f"cache:subscription:status:{user_id}"
    
    @staticmethod
    def tasks_today(user_id: str) -> str:
        """Today's tasks cache key (legacy)."""
        return f"cache:tasks:today:{user_id}"
    
    @staticmethod
    def daily_tasks(user_id: str, date: str) -> str:
        """Daily tasks cache key for the v2 HomeScreen endpoint."""
        return f"cache:tasks:daily:{user_id}:{date}"
    
    @staticmethod
    def task_plan(plan_id: str) -> str:
        """Daily plan cache key."""
        return f"cache:tasks:plan:{plan_id}"
    
    @staticmethod
    def journal_recent(user_id: str) -> str:
        """Recent journal entries cache key."""
        return f"cache:journal:recent:{user_id}"
    
    @staticmethod
    def journal_entry(entry_id: str) -> str:
        """Single journal entry cache key."""
        return f"cache:journal:entry:{entry_id}"
    
    @staticmethod
    def journal_list(user_id: str, page: int, filters: str = "") -> str:
        """Journal list cache key with pagination."""
        return f"cache:journal:list:{user_id}:page:{page}:{filters}"
    
    @staticmethod
    def journal_limit(user_id: str, month: str) -> str:
        """Journal limit counter cache key."""
        return f"cache:journal:limit:{user_id}:{month}"
    
    @staticmethod
    def packages(platform: str) -> str:
        """Subscription packages cache key."""
        return f"cache:subscription:packages:{platform}"

    # Cache-first task keys ------------------------------------------------

    @staticmethod
    def task_data(user_id: str, date: str) -> str:
        """Redis Hash holding individual task JSON dicts for a user+date."""
        return f"tasks:data:{user_id}:{date}"

    @staticmethod
    def task_meta(user_id: str, date: str) -> str:
        """Redis Hash with {total, completed} counters for a user+date."""
        return f"tasks:meta:{user_id}:{date}"

    @staticmethod
    def task_sync_stream() -> str:
        """Redis Stream used for write-behind sync to PostgreSQL."""
        return "stream:tasks:sync"


# =============================================================================
# Cache Invalidation Helpers
# =============================================================================

class CacheInvalidator:
    """Helpers for invalidating related cache entries."""
    
    @staticmethod
    async def on_task_complete(user_id: str, date: str) -> None:
        """Invalidate caches when a task is completed."""
        await CacheManager.delete(CacheKeys.tasks_today(user_id))
        await CacheManager.delete(CacheKeys.daily_tasks(user_id, date))
    
    @staticmethod
    async def on_journal_create(user_id: str, date: str) -> None:
        """Invalidate caches when a journal entry is created."""
        await CacheManager.delete(CacheKeys.journal_recent(user_id))
        await CacheManager.delete_pattern(f"cache:journal:list:{user_id}:*")
    
    @staticmethod
    async def on_profile_update(user_id: str) -> None:
        """Invalidate caches when profile is updated."""
        await CacheManager.delete(CacheKeys.profile(user_id))
        await CacheManager.delete(CacheKeys.user_auth(user_id))
    
    @staticmethod
    async def on_subscription_change(user_id: str) -> None:
        """Invalidate caches when subscription changes."""
        await CacheManager.delete(CacheKeys.subscription(user_id))
        await CacheManager.delete(CacheKeys.subscription_status(user_id))
        await CacheManager.delete(CacheKeys.profile(user_id))
        await CacheManager.delete(CacheKeys.user_auth(user_id))
