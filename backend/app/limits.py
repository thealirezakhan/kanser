from collections import defaultdict, deque
from time import monotonic


class SlidingWindowLimiter:
    def __init__(self, max_calls: int, period: float = 60.0) -> None:
        self.max_calls = max_calls
        self.period = period
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = monotonic()
        q = self._hits[key]
        while q and q[0] <= now - self.period:
            q.popleft()
        if len(q) >= self.max_calls:
            return False
        q.append(now)
        return True

    def reset(self) -> None:
        self._hits.clear()


global_limiter = SlidingWindowLimiter(max_calls=60, period=60.0)
diagnose_limiter = SlidingWindowLimiter(max_calls=5, period=60.0)
