"""SystemClock: the one real implementation of the Clock protocol."""

from datetime import datetime, timezone

from src.core.clock import SystemClock


def test_now_returns_a_timezone_aware_datetime() -> None:
    now = SystemClock().now()

    assert now.tzinfo is not None


def test_now_is_close_to_real_wall_clock_time() -> None:
    before = datetime.now(timezone.utc)

    observed = SystemClock().now()

    after = datetime.now(timezone.utc)
    assert before <= observed <= after


def test_now_advances_between_calls() -> None:
    clock = SystemClock()

    first = clock.now()
    second = clock.now()

    assert second >= first
