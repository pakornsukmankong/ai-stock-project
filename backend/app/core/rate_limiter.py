import time
from collections import defaultdict
from fastapi import Request, HTTPException


class RateLimiter:
    """In-memory rate limiter using sliding window.

    Limits requests per IP address within a time window.
    """

    def __init__(self, max_requests: int = 60, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: dict[str, list[float]] = defaultdict(list)

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request."""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def check(self, request: Request) -> None:
        """Check if request is within rate limit. Raises 429 if exceeded."""
        client_ip = self._get_client_ip(request)
        now = time.time()
        window_start = now - self.window_seconds

        # Remove expired timestamps
        self.requests[client_ip] = [
            ts for ts in self.requests[client_ip] if ts > window_start
        ]

        # Check limit
        if len(self.requests[client_ip]) >= self.max_requests:
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please try again later.",
                headers={"Retry-After": str(self.window_seconds)},
            )

        # Record this request
        self.requests[client_ip].append(now)

    def cleanup(self) -> None:
        """Remove stale entries to prevent memory leak."""
        now = time.time()
        window_start = now - self.window_seconds
        stale_keys = [
            ip for ip, timestamps in self.requests.items()
            if not timestamps or timestamps[-1] < window_start
        ]
        for key in stale_keys:
            del self.requests[key]


# Global rate limiter instance
api_limiter = RateLimiter(max_requests=60, window_seconds=60)  # 60 req/min per IP
