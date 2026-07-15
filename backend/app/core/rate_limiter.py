import time
from collections import defaultdict
from typing import Optional

from fastapi import Request, HTTPException

from app.core.config import get_settings


class RateLimiter:
    """In-memory rate limiter using sliding window.

    Limits requests per client key (IP address, or user id for per-user limits)
    within a time window.
    """

    def __init__(self, max_requests: int = 60, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: dict[str, list[float]] = defaultdict(list)

    def _get_client_ip(self, request: Request) -> str:
        """Resolve the real client IP, ignoring attacker-supplied hops.

        X-Forwarded-For is a client-writable header: the proxy *appends* the peer
        it saw, so only the entries our own proxies added can be trusted. Reading
        the leftmost value (the previous behaviour) let anyone bypass the limit
        entirely by sending a random X-Forwarded-For on each request. We instead
        count `trusted_proxy_hops` from the right.
        """
        hops = get_settings().trusted_proxy_hops
        forwarded = request.headers.get("X-Forwarded-For")

        if forwarded and hops > 0:
            chain = [part.strip() for part in forwarded.split(",") if part.strip()]
            if chain:
                # hops=1 → the address our edge proxy saw is the last entry.
                index = max(0, len(chain) - hops)
                return chain[index]

        return request.client.host if request.client else "unknown"

    def check(self, request: Request, key: Optional[str] = None) -> None:
        """Check if request is within rate limit. Raises 429 if exceeded.

        Args:
            key: Explicit bucket key (e.g. a user id). Defaults to the client IP.
        """
        client_key = key or self._get_client_ip(request)
        now = time.time()
        window_start = now - self.window_seconds

        # Remove expired timestamps
        self.requests[client_key] = [
            ts for ts in self.requests[client_key] if ts > window_start
        ]

        # Check limit
        if len(self.requests[client_key]) >= self.max_requests:
            retry_after = int(self.requests[client_key][0] + self.window_seconds - now) + 1
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please try again later.",
                headers={"Retry-After": str(max(1, retry_after))},
            )

        # Record this request
        self.requests[client_key].append(now)

    def cleanup(self) -> None:
        """Remove stale entries to prevent memory leak."""
        now = time.time()
        window_start = now - self.window_seconds
        stale_keys = [
            k for k, timestamps in self.requests.items()
            if not timestamps or timestamps[-1] < window_start
        ]
        for key in stale_keys:
            del self.requests[key]


# Global rate limiter instance
api_limiter = RateLimiter(max_requests=60, window_seconds=60)  # 60 req/min per IP

# Manual analysis triggers are expensive (fans out to every watched symbol and
# calls OpenAI), so they get their own much stricter per-user budget.
trigger_limiter = RateLimiter(
    max_requests=1, window_seconds=get_settings().trigger_cooldown_seconds
)
