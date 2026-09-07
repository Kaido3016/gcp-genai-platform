import pytest

from app.services.ai.retry import RetryExhaustedError, call_with_retry


class FlakyError(Exception):
    pass


class OtherError(Exception):
    pass


def test_succeeds_first_try():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        return "ok"

    result = call_with_retry(
        fn,
        max_retries=3,
        backoff_base_seconds=0.0,
        retryable_exceptions=(FlakyError,),
        sleep_fn=lambda s: None,
    )
    assert result == "ok"
    assert calls["n"] == 1


def test_retries_then_succeeds():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] < 3:
            raise FlakyError("transient")
        return "ok"

    result = call_with_retry(
        fn,
        max_retries=5,
        backoff_base_seconds=0.0,
        retryable_exceptions=(FlakyError,),
        sleep_fn=lambda s: None,
    )
    assert result == "ok"
    assert calls["n"] == 3


def test_exhausts_and_raises():
    def fn():
        raise FlakyError("always fails")

    with pytest.raises(RetryExhaustedError) as exc_info:
        call_with_retry(
            fn,
            max_retries=2,
            backoff_base_seconds=0.0,
            retryable_exceptions=(FlakyError,),
            sleep_fn=lambda s: None,
        )
    assert exc_info.value.attempts == 3  # initial try + 2 retries


def test_non_retryable_propagates_immediately():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise OtherError("not retryable")

    with pytest.raises(OtherError):
        call_with_retry(
            fn,
            max_retries=5,
            backoff_base_seconds=0.0,
            retryable_exceptions=(FlakyError,),
            sleep_fn=lambda s: None,
        )
    assert calls["n"] == 1
