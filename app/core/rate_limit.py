"""
Rate Limiting
=============

Redis-based rate limiting for API endpoints using sliding window algorithm.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Request, status

from app.services.cache import get_redis


class RateLimiter:
    """
    Sliding window rate limiter using Redis.
    
    Rate limits are applied per user (if authenticated) or per IP.
    
    Default limits:
        - Authentication endpoints: 5 requests/minute
        - Creation endpoints: 30 requests/minute
        - Read endpoints: 100 requests/minute
        - Voice upload: 10 requests/minute
    """
    
    # Limit configurations
    LIMITS = {
        "auth": {"max_requests": 5, "window_seconds": 60},
        "create": {"max_requests": 30, "window_seconds": 60},
        "read": {"max_requests": 100, "window_seconds": 60},
        "voice": {"max_requests": 10, "window_seconds": 60},
    }
    
    @staticmethod
    def _get_key(identifier: str, action: str) -> str:
        """Generate rate limit key."""
        return f"ratelimit:{action}:{identifier}"
    
    @staticmethod
    async def check_rate_limit(
        identifier: str,
        action: str,
        max_requests: Optional[int] = None,
        window_seconds: Optional[int] = None,
    ) -> dict:
        """
        Check if request is within rate limit.
        
        Args:
            identifier: User ID or IP address
            action: Action type (auth, create, read, voice)
            max_requests: Override max requests (optional)
            window_seconds: Override window size (optional)
            
        Returns:
            Dict with 'allowed', 'remaining', 'reset_in' keys
        """
        # Get limits
        limits = RateLimiter.LIMITS.get(action, RateLimiter.LIMITS["read"])
        max_req = max_requests or limits["max_requests"]
        window = window_seconds or limits["window_seconds"]
        
        key = RateLimiter._get_key(identifier, action)
        
        try:
            client = await get_redis()
            
            # Get current count
            current = await client.get(key)
            
            if current is None:
                # First request in window
                await client.setex(key, window, 1)
                return {
                    "allowed": True,
                    "remaining": max_req - 1,
                    "reset_in": window,
                }
            
            current_count = int(current)
            
            if current_count >= max_req:
                # Rate limited
                ttl = await client.ttl(key)
                return {
                    "allowed": False,
                    "remaining": 0,
                    "reset_in": ttl if ttl > 0 else window,
                }
            
            # Increment counter
            await client.incr(key)
            ttl = await client.ttl(key)
            
            return {
                "allowed": True,
                "remaining": max_req - current_count - 1,
                "reset_in": ttl if ttl > 0 else window,
            }
            
        except Exception as e:
            print(f"Rate limit check error: {e}")
            # Allow request on error (fail open)
            return {
                "allowed": True,
                "remaining": max_req,
                "reset_in": window,
            }
    
    @staticmethod
    async def is_allowed(
        identifier: str,
        action: str,
        max_requests: Optional[int] = None,
        window_seconds: Optional[int] = None,
    ) -> bool:
        """
        Simple check if request is allowed.
        
        Args:
            identifier: User ID or IP address
            action: Action type
            max_requests: Override max requests
            window_seconds: Override window
            
        Returns:
            True if allowed, False if rate limited
        """
        result = await RateLimiter.check_rate_limit(
            identifier, action, max_requests, window_seconds
        )
        return result["allowed"]


async def rate_limit_dependency(
    request: Request,
    action: str = "read",
) -> None:
    """
    FastAPI dependency for rate limiting.
    
    Usage:
        @app.get("/endpoint")
        async def endpoint(
            _: None = Depends(lambda r: rate_limit_dependency(r, "read"))
        ):
            ...
    """
    # Get identifier (user ID from auth or IP)
    identifier = request.client.host if request.client else "unknown"
    
    # Check if user is authenticated
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        # In a real implementation, decode the token to get user_id
        # For now, use the token itself as identifier
        identifier = auth_header[7:20]  # First 13 chars of token
    
    result = await RateLimiter.check_rate_limit(identifier, action)
    
    if not result["allowed"]:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "RATE_LIMIT",
                "message": f"Rate limit exceeded. Try again in {result['reset_in']} seconds.",
            },
            headers={
                "X-RateLimit-Limit": str(RateLimiter.LIMITS.get(action, {}).get("max_requests", 100)),
                "X-RateLimit-Remaining": str(result["remaining"]),
                "X-RateLimit-Reset": str(result["reset_in"]),
                "Retry-After": str(result["reset_in"]),
            },
        )


def create_rate_limit_dependency(action: str = "read"):
    """
    Factory for rate limit dependencies.
    
    Usage:
        @app.get("/endpoint", dependencies=[Depends(create_rate_limit_dependency("read"))])
        async def endpoint():
            ...
    """
    async def dependency(request: Request) -> None:
        await rate_limit_dependency(request, action)
    
    return dependency
