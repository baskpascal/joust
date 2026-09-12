from datetime import datetime, timedelta, timezone

import pytest

from hackathon_competitor.deadline import DeadlinePolicy


@pytest.mark.parametrize(
    ("hours", "mode", "frozen"),
    [
        (100, "explore", False),
        (48, "build", False),
        (12, "stabilize", True),
        (3, "submission", True),
        (0.5, "emergency", True),
    ],
)
def test_deadline_modes(hours, mode, frozen):
    now = datetime(2026, 9, 12, tzinfo=timezone.utc)
    guidance = DeadlinePolicy().assess(now + timedelta(hours=hours), now=now)
    assert guidance.mode == mode
    assert guidance.architecture_frozen is frozen


def test_deadline_requires_timezone():
    with pytest.raises(ValueError, match="timezone-aware"):
        DeadlinePolicy().assess(datetime(2026, 9, 12))
