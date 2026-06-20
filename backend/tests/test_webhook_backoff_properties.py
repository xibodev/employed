"""Property-based test for the webhook delivery backoff schedule (Property 20).

:func:`app.workers.tasks.compute_backoff_delay` schedules the next webhook
retry ``min(2**attempts * WEBHOOK_BACKOFF_BASE_SECONDS, WEBHOOK_BACKOFF_CAP)``
into the future, where ``attempts`` is the number of attempts already made. The
resulting schedule must be monotonically non-decreasing in ``attempts`` and
bounded above by :data:`WEBHOOK_BACKOFF_CAP`; once
:data:`WEBHOOK_MAX_ATTEMPTS` is reached the delivery becomes terminally
``failed`` (R20.5).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.workers.tasks import (
    WEBHOOK_BACKOFF_BASE_SECONDS,
    WEBHOOK_BACKOFF_CAP,
    compute_backoff_delay,
)

# A mix of boundary (0), small, and very large attempt counts so the test
# exercises both the exponential-growth region and the saturated cap region.
_attempts = st.one_of(
    st.integers(min_value=0, max_value=5),
    st.integers(min_value=0, max_value=64),
    st.integers(min_value=10**6, max_value=10**18),
)


# Feature: multi-tenant-hiring-platform, Property 20: Webhook retries follow a bounded backoff schedule
@settings(max_examples=100, deadline=None)
@given(attempts=_attempts)
def test_backoff_is_bounded_and_monotonic(attempts: int) -> None:
    """The next-attempt delay is always within ``(0, cap]`` and the schedule is
    monotonically non-decreasing: ``delay(n) <= delay(n + 1)``.

    Validates: Requirements 20.5
    """
    delay = compute_backoff_delay(attempts)
    next_delay = compute_backoff_delay(attempts + 1)

    # Bounded above by the cap regardless of how large ``attempts`` grows, and
    # never collapses below the base interval.
    assert timedelta(seconds=WEBHOOK_BACKOFF_BASE_SECONDS) <= delay <= WEBHOOK_BACKOFF_CAP
    assert next_delay <= WEBHOOK_BACKOFF_CAP

    # Monotonically non-decreasing in the number of attempts.
    assert delay <= next_delay


# Feature: multi-tenant-hiring-platform, Property 20: Webhook retries follow a bounded backoff schedule
def test_backoff_base_and_saturation() -> None:
    """The first delay equals the base interval and the schedule eventually
    saturates at the cap (and stays there).

    Validates: Requirements 20.5
    """
    assert compute_backoff_delay(0) == timedelta(seconds=WEBHOOK_BACKOFF_BASE_SECONDS)

    # 2**n * 30s reaches 6h once n is large enough; well before then the value
    # is clamped to the cap and never exceeds it.
    saturated = compute_backoff_delay(20)
    assert saturated == WEBHOOK_BACKOFF_CAP
    assert compute_backoff_delay(10**12) == WEBHOOK_BACKOFF_CAP


if __name__ == "__main__":  # pragma: no cover - convenience for ad-hoc runs
    pytest.main([__file__, "-v"])
