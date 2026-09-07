"""Small, explicit retry-with-backoff helper."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

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
    """Run `fn`, retrying only on configured transient exceptions."""
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except retryable_exceptions as exc:  # noqa: PERF203
            last_error = exc
            if attempt == max_retries:
                break
            sleep_fn(backoff_base_seconds * (2**attempt))
    assert last_error is not None
    raise RetryExhaustedError(max_retries + 1, last_error)
