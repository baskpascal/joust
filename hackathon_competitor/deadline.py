from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .models import DeadlineGuidance


@dataclass(frozen=True)
class DeadlineThresholds:
    broad_research_hours: float = 72.0
    build_focus_hours: float = 24.0
    freeze_hours: float = 6.0
    emergency_hours: float = 1.0


class DeadlinePolicy:
    def __init__(self, thresholds: DeadlineThresholds | None = None):
        self.thresholds = thresholds or DeadlineThresholds()

    def assess(self, deadline: datetime, *, now: datetime | None = None) -> DeadlineGuidance:
        now = now or datetime.now(timezone.utc)
        if deadline.tzinfo is None or now.tzinfo is None:
            raise ValueError("deadline policy requires timezone-aware datetimes")
        hours = (deadline - now).total_seconds() / 3600
        if hours < self.thresholds.emergency_hours:
            return DeadlineGuidance(
                mode="emergency",
                hours_remaining=hours,
                max_reasoning_depth=2,
                architecture_frozen=True,
                risky_changes_require_confirmation=True,
                priorities=["submission completeness", "demo reliability", "backups", "compliance"],
            )
        if hours < self.thresholds.freeze_hours:
            return DeadlineGuidance(
                mode="submission",
                hours_remaining=hours,
                max_reasoning_depth=3,
                architecture_frozen=True,
                risky_changes_require_confirmation=True,
                priorities=["install test", "demo test", "README", "submission completeness"],
            )
        if hours < self.thresholds.build_focus_hours:
            return DeadlineGuidance(
                mode="stabilize",
                hours_remaining=hours,
                max_reasoning_depth=4,
                architecture_frozen=True,
                risky_changes_require_confirmation=False,
                priorities=["correctness", "integration", "demo", "submission"],
            )
        if hours < self.thresholds.broad_research_hours:
            return DeadlineGuidance(
                mode="build",
                hours_remaining=hours,
                max_reasoning_depth=5,
                architecture_frozen=False,
                risky_changes_require_confirmation=False,
                priorities=["build", "critical experiments", "product validation"],
            )
        return DeadlineGuidance(
            mode="explore",
            hours_remaining=hours,
            max_reasoning_depth=5,
            architecture_frozen=False,
            risky_changes_require_confirmation=False,
            priorities=[
                "strategy research",
                "architecture tournament",
                "prototypes",
                "experiments",
            ],
        )
