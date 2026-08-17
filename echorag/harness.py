"""Orchestration around the pipeline: deadlines, retries, circuit breaking.

This is what makes the 200 ms SLO a property of the code rather than of a good
day (AUDIT §8).
"""

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")

BUDGET_MS = 200.0


class Deadline:
    """A monotonic budget threaded through every stage.

    perf_counter, not time.time — the wall clock can jump backwards (NTP) and
    would silently hand a stage a negative or enormous budget.
    """

    def __init__(self, budget_ms: float = BUDGET_MS):
        self.budget_ms = budget_ms
        self._start = time.perf_counter()

    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self._start) * 1000

    def remaining_ms(self) -> float:
        return max(0.0, self.budget_ms - self.elapsed_ms())

    def expired(self) -> bool:
        return self.remaining_ms() <= 0

    def __repr__(self) -> str:
        return f"<Deadline {self.elapsed_ms():.1f}/{self.budget_ms:.0f}ms>"


class CircuitBreaker:
    """Stops calling a dependency that is already failing.

    Without this, an outage turns every request into a full timeout wait —
    the deadline still holds, but every user pays the maximum latency.
    """

    def __init__(self, threshold: int = 3, cooldown_s: float = 30.0):
        self.threshold = threshold
        self.cooldown_s = cooldown_s
        self._failures = 0
        self._opened_at: float | None = None

    @property
    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        if time.monotonic() - self._opened_at >= self.cooldown_s:
            self._failures = 0
            self._opened_at = None
            return False
        return True

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.threshold:
            self._opened_at = time.monotonic()


async def with_deadline(coro: Awaitable[T], deadline: Deadline) -> T | None:
    """Run `coro`, returning None if it doesn't finish inside the budget.

    Returning None rather than raising is deliberate: a slow optional stage is
    a normal outcome here, not an error, and the caller falls through to its
    fallback (AUDIT §8 fallback chain).
    """
    remaining = deadline.remaining_ms()
    if remaining <= 0:
        # The caller already built the coroutine, so bailing out without
        # awaiting leaks it and emits "coroutine was never awaited". Closing it
        # is the only path here that runs no user code. (asyncio.wait_for below
        # cancels correctly on timeout, so only this early return needs it.)
        close = getattr(coro, "close", None)
        if close is not None:
            close()
        return None
    try:
        return await asyncio.wait_for(coro, timeout=remaining / 1000)
    except (TimeoutError, asyncio.CancelledError):
        return None


async def retry(
    fn: Callable[[], Awaitable[T]],
    attempts: int = 3,
    base_delay: float = 0.2,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
) -> T:
    """Bounded retry with jittered exponential backoff.

    Jitter matters: without it, every client that failed at the same moment
    retries at the same moment and hits the recovering service together.
    """
    last: BaseException | None = None
    for attempt in range(attempts):
        try:
            return await fn()
        except retry_on as exc:
            last = exc
            if attempt == attempts - 1:
                break
            await asyncio.sleep(base_delay * 2**attempt + random.uniform(0, 0.1))
    raise last  # type: ignore[misc]


if __name__ == "__main__":
    import asyncio as _a

    async def demo():
        d = Deadline(budget_ms=50)
        assert d.remaining_ms() <= 50 and not d.expired()

        async def slow():
            await _a.sleep(1)
            return "never"

        assert await with_deadline(slow(), d) is None, "slow work must be dropped"
        assert d.expired(), "budget should be spent"

        cb = CircuitBreaker(threshold=2, cooldown_s=99)
        assert not cb.is_open
        cb.record_failure()
        assert not cb.is_open, "one failure must not open the circuit"
        cb.record_failure()
        assert cb.is_open, "threshold reached — circuit should open"
        cb.record_success()
        assert not cb.is_open, "success must reset it"

        calls = 0

        async def flaky():
            nonlocal calls
            calls += 1
            if calls < 3:
                raise RuntimeError("boom")
            return "ok"

        assert await retry(flaky, base_delay=0.001) == "ok"
        assert calls == 3
        print("✅ harness checks passed")

    _a.run(demo())
