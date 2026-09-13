"""Small, dependency-free operational protections for a public demo."""

import threading
import time
from collections import defaultdict, deque


class RequestRateLimiter:
    """In-memory fixed-window request limiter; replace with Redis when scaled."""

    def __init__(self, limit: int, window_seconds: int = 60):
        self.limit = limit
        self.window_seconds = window_seconds
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, client_id: str, now: float | None = None) -> bool:
        """Record a request only when it fits within the configured window."""
        timestamp = now if now is not None else time.monotonic()
        with self._lock:
            requests = self._requests[client_id]
            while requests and timestamp - requests[0] >= self.window_seconds:
                requests.popleft()
            if len(requests) >= self.limit:
                return False
            requests.append(timestamp)
            return True


class TaskConcurrencyLimiter:
    """Bound concurrent task execution and reject excess work immediately."""

    def __init__(self, maximum: int):
        self._semaphore = threading.BoundedSemaphore(maximum)

    def try_acquire(self) -> bool:
        return self._semaphore.acquire(blocking=False)

    def release(self) -> None:
        self._semaphore.release()
