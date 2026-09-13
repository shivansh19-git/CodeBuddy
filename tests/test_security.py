from app.security import RequestRateLimiter, TaskConcurrencyLimiter


def test_rate_limiter_releases_requests_after_its_window():
    limiter = RequestRateLimiter(limit=2, window_seconds=60)
    assert limiter.allow("client", now=0)
    assert limiter.allow("client", now=1)
    assert not limiter.allow("client", now=2)
    assert limiter.allow("client", now=60)


def test_task_limiter_rejects_excess_concurrent_work():
    limiter = TaskConcurrencyLimiter(1)
    assert limiter.try_acquire()
    assert not limiter.try_acquire()
    limiter.release()
    assert limiter.try_acquire()
