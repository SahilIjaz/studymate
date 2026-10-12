"""In-process token-bucket rate limiter.

Good enough for a single instance. Behind a load balancer with several
replicas, back this with Redis (same interface, shared counters).
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass


@dataclass(slots=True)
class _Bucket:
    tokens: float
    updated: float


class TokenBucketLimiter:
    def __init__(self, *, capacity: int, refill_per_minute: int) -> None:
        self.capacity = float(capacity)
        self.refill_per_second = refill_per_minute / 60.0
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()
        self._last_sweep = time.monotonic()

    def _sweep(self, now: float) -> None:
        """Drop buckets that have been full for a while to bound memory."""
        if now - self._last_sweep < 300:
            return
        self._last_sweep = now
        full_after = self.capacity / self.refill_per_second if self.refill_per_second else 0
        stale = [k for k, b in self._buckets.items() if now - b.updated > full_after + 60]
        for key in stale:
            del self._buckets[key]

    def try_acquire(self, key: str, cost: float = 1.0) -> tuple[bool, float]:
        """Return (allowed, seconds_until_next_token)."""
        now = time.monotonic()
        with self._lock:
            self._sweep(now)
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(tokens=self.capacity, updated=now)
                self._buckets[key] = bucket
            elapsed = now - bucket.updated
            bucket.tokens = min(self.capacity, bucket.tokens + elapsed * self.refill_per_second)
            bucket.updated = now
            if bucket.tokens >= cost:
                bucket.tokens -= cost
                return True, 0.0
            deficit = cost - bucket.tokens
            wait = deficit / self.refill_per_second if self.refill_per_second else math.inf
            return False, wait
