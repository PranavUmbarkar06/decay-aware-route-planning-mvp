"""In-process sliding-window rate limiter for auth and PIN endpoints (single-instance prototype; a shared
store such as Redis is needed for multi-instance deployments; see docs/SECURITY.md)."""
from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status


class SlidingWindow:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window_s: float = 60.0) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > window_s:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = SlidingWindow()


def client_key(request: Request, scope: str) -> str:
    host = request.client.host if request.client else "unknown"
    return f"{scope}:{host}"


# Only the isolated E2E stack sets this (all test browsers share one client address). Never set it in a deployment.
_MULTIPLIER = int(os.environ.get("PHL_RATE_LIMIT_MULTIPLIER", "1"))


def enforce(request: Request, scope: str, limit: int, window_s: float = 60.0) -> None:
    if not limiter.hit(client_key(request, scope), limit * _MULTIPLIER, window_s):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Please wait a minute and try again.")
