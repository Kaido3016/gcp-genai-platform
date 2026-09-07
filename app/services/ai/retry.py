"""Small, explicit retry-with-backoff helper.

Phase 15 requirement: graceful handling of transient Vertex AI failures
with exponential backoff, without hiding non-retryable errors.
"""

from __future__ import annotations

import time
from typing import Callable, TypeVar

T = TypeVar("T")


class RetryExhaustedError(Exception):
    def __init__(self, attempts: int, last_error: Exception):
        super().__init__(f"Retry exhausted after {attempts} attempts: {last_error}")
        self.attempts = attempts
        self.last_error = last_error


def call_with_retry(
    fn: Callable[[], T],
    *,
    max_retries: int,
    backoff_base_seconds: float,
    retryable_exceptions: tuple[type[Exception], ...],
    sleep_fn: Callable[[float], None] = time.sleep,
) -> T:
    """Runs `fn`, retrying only on `retryable_exceptions` with exponential
    backoff (backoff_base * 2**attempt). Non-retryable exceptions propagate
    immediately. Raises RetryExhaustedError if all attempts fail."""
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except retryable_exceptions as exc:  # noqa: PERF203 - clarity over micro-perf
            last_error = exc
            if attempt == max_retries:
                break
            sleep_fn(backoff_base_seconds * (2**attempt))
    assert last_error is not None
    raise RetryExhaustedError(max_retries + 1, last_error)
