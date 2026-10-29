"""
app/security/middleware.py
--------------------------
Security middlewares for FastAPI:
1. API Key Authentication (X-API-Key header verification).
2. Sliding-Window Client IP Rate Limiting (DoS prevention).
3. Safe Error Handling & Header Hardening.
"""

import time
import logging
from collections import defaultdict
from typing import Dict, List, Optional
from datetime import datetime, timezone
from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.config import settings

logger = logging.getLogger("agentic_ai.security")

# Paths that do not require authentication or strict rate limits
EXEMPT_PATHS = {"/health", "/docs", "/redoc", "/openapi.json", "/"}


class SlidingWindowRateLimiter:
    """
    In-memory sliding-window rate limiter per client IP address.
    Tracks timestamps of requests within a sliding 60-second window.
    """

    def __init__(self, limit_per_minute: int = 60, window_seconds: int = 60):
        self.limit = limit_per_minute
        self.window = window_seconds
        self.requests: Dict[str, List[float]] = defaultdict(list)

    def is_allowed(self, client_ip: str, limit: Optional[int] = None) -> bool:
        """Determines if a request from the given IP is within the rate limit."""
        max_allowed = limit if limit is not None else settings.RATE_LIMIT_PER_MINUTE
        now = time.time()
        cutoff = now - self.window

        # Clean timestamps older than the sliding window
        valid_timestamps = [ts for ts in self.requests[client_ip] if ts > cutoff]
        self.requests[client_ip] = valid_timestamps

        if len(valid_timestamps) >= max_allowed:
            return False

        self.requests[client_ip].append(now)
        return True

    def reset(self):
        """Resets the rate limiter state (useful for tests)."""
        self.requests.clear()


# Global rate limiter instance
rate_limiter = SlidingWindowRateLimiter(limit_per_minute=settings.RATE_LIMIT_PER_MINUTE)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enforces sliding-window rate limiting per client IP.
    """

    async def dispatch(self, request: Request, call_next):
        if not settings.RATE_LIMIT_ENABLED or request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        # Determine client IP (handles reverse proxy X-Forwarded-For if present)
        forwarded = request.headers.get("x-forwarded-for")
        client_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")

        if not rate_limiter.is_allowed(client_ip):
            logger.warning(f"Rate limit exceeded for client IP: {client_ip}")
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "Rate limit exceeded",
                    "details": f"Too many requests. Limit is {settings.RATE_LIMIT_PER_MINUTE} requests per minute.",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                },
                headers={"Retry-After": "60"}
            )

        return await call_next(request)


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware verifying X-API-Key header when API_AUTH_ENABLED is True.
    Exempts public endpoints (/health, /docs, /openapi.json).
    """

    async def dispatch(self, request: Request, call_next):
        if not settings.API_AUTH_ENABLED or request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        api_key = request.headers.get("x-api-key")
        expected_key = settings.API_KEY

        if not expected_key or api_key != expected_key:
            logger.warning(f"Unauthorized API request attempt from {request.client.host if request.client else 'unknown'}")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "error": "Unauthorized",
                    "details": "Invalid or missing X-API-Key authentication header.",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            )

        return await call_next(request)
