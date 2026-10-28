"""In-memory sliding-window rate limiter.

Per-process only: with more than one instance, move the counters to Redis (see docs/03-architecture.md).
"""
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from .config import Settings


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window_seconds: float) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > window_seconds:
                hits.popleft()
            if len(hits) >= limit:
                return False
            hits.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def client_ip(request: Request, settings: Settings) -> str:
    if settings.trust_proxy:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def enforce(request: Request, settings: Settings, name: str, limit: int, window_seconds: float,
            extra_key: str = "") -> None:
    if not settings.rate_limit_enabled:
        return
    key = f"{name}:{client_ip(request, settings)}:{extra_key}"
    if not limiter.allow(key, limit, window_seconds):
        raise HTTPException(429, "too many requests, slow down", headers={"Retry-After": str(int(window_seconds))})
