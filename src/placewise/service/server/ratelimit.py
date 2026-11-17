"""Token-bucket rate limiting, one bucket per API key (or per client address without keys)."""

import threading
import time

from placewise.constants import server as const


class _Bucket:
    __slots__ = ("capacity", "rate", "stamp", "tokens")

    def __init__(self, rate, capacity, now):
        self.rate, self.capacity, self.tokens, self.stamp = rate, capacity, capacity, now

    def refill(self, now):
        self.tokens = min(self.capacity, self.tokens + (now - self.stamp) * self.rate)
        self.stamp = now


class RateLimiter:
    """`take(name, per_minute, cost)` returns 0 when the request may go ahead, otherwise the seconds
    to wait. A bucket holds BURST_SECONDS worth of its rate. A request is let through whenever at
    least one token is left, and its whole cost is then taken, so one large batch is answered and
    the bucket goes into debt that later requests wait out."""

    def __init__(
        self, clock=time.monotonic, *, burst_seconds=const.BURST_SECONDS, max_buckets=const.MAX_BUCKETS
    ):
        self.clock = clock
        self.burst_seconds = burst_seconds
        self.max_buckets = max_buckets
        self._buckets = {}
        self._lock = threading.Lock()

    def __len__(self):
        return len(self._buckets)

    def take(self, name, per_minute, cost=1):
        if not per_minute or per_minute <= 0:
            return 0.0
        rate = per_minute / 60.0
        capacity = max(1.0, rate * self.burst_seconds)
        with self._lock:
            now = self.clock()
            bucket = self._buckets.get(name)
            if bucket is None or bucket.rate != rate:
                if len(self._buckets) >= self.max_buckets:
                    self._prune(now)
                bucket = self._buckets[name] = _Bucket(rate, capacity, now)
            else:
                bucket.refill(now)
            if bucket.tokens >= 1.0:
                bucket.tokens -= cost
                return 0.0
            return (1.0 - bucket.tokens) / rate

    def charge(self, name, per_minute, cost):
        """Take `cost` more tokens unconditionally (the rest of a batch already let through)."""
        if not per_minute or per_minute <= 0 or cost <= 0:
            return
        with self._lock:
            bucket = self._buckets.get(name)
            if bucket is not None:
                bucket.refill(self.clock())
                bucket.tokens -= cost

    def _prune(self, now):
        """Forget full buckets (forgetting them changes nothing); if none are full, the stalest half."""
        for name, bucket in list(self._buckets.items()):
            bucket.refill(now)
            if bucket.tokens >= bucket.capacity:
                del self._buckets[name]
        if len(self._buckets) >= self.max_buckets:
            stale = sorted(self._buckets, key=lambda n: self._buckets[n].stamp)
            for name in stale[: len(stale) // 2 + 1]:
                del self._buckets[name]
