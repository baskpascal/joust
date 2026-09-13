from __future__ import annotations

from uuid import UUID

from .models import (
    CompetitionMetricInterpretation,
    CompetitionMetricsDelta,
    PlowMetricsSnapshot,
)
from .storage import Database


def _difference(current: int | None, previous: int | None) -> int | None:
    if current is None or previous is None:
        return None
    return current - previous


def _growth(current: int | None, previous: int | None) -> float | None:
    if current is None or previous is None or previous <= 0:
        return None
    return (current - previous) / previous


class CompetitionMetricsAnalyzer:
    def analyze(
        self,
        current: PlowMetricsSnapshot,
        previous: PlowMetricsSnapshot | None = None,
        *,
        competitor_growth_rate: float | None = None,
    ) -> CompetitionMetricInterpretation:
        delta = CompetitionMetricsDelta(competitor_growth_rate=competitor_growth_rate)
        if previous is not None:
            # Positive rank change means improvement; 4 -> 7 is -3.
            delta.rank_change = (
                previous.rank - current.rank
                if previous.rank is not None and current.rank is not None
                else None
            )
            delta.users_delta = _difference(current.users, previous.users)
            delta.successful_installs_delta = _difference(
                current.successful_installs, previous.successful_installs
            )
            delta.token_usage_delta = _difference(current.token_usage, previous.token_usage)
            delta.token_growth_rate = _growth(current.token_usage, previous.token_usage)
            delta.acquisition_growth_rate = _growth(current.users, previous.users)

        if not current.verified:
            return CompetitionMetricInterpretation(
                bottleneck="Agent Index eligibility: Joust is not Verified",
                next_best_action="Prepare an approval-bound Agent Index verification request",
                rationale="Only Verified agents are eligible to rank; rank is unavailable until then.",
                delta=delta,
            )
        if (
            delta.rank_change is not None
            and delta.rank_change < 0
            and competitor_growth_rate is not None
            and (
                delta.acquisition_growth_rate is None
                or competitor_growth_rate > delta.acquisition_growth_rate
            )
        ):
            return CompetitionMetricInterpretation(
                bottleneck="Acquisition velocity is below competitor growth",
                next_best_action="Improve the install path and distribution campaign",
                rationale=(
                    "Rank declined while competitor growth outpaced user growth; "
                    "the evidence does not identify retention as the bottleneck."
                ),
                delta=delta,
            )
        if current.successful_installs == 0 or (
            delta.successful_installs_delta is not None
            and delta.successful_installs_delta <= 0
            and (delta.users_delta is None or delta.users_delta <= 0)
        ):
            return CompetitionMetricInterpretation(
                bottleneck="Successful-install acquisition is stalled",
                next_best_action="Remove install friction and produce installable proof",
                rationale="Successful installs are zero or did not grow in the observed interval.",
                delta=delta,
            )
        if delta.token_usage_delta is not None and delta.token_usage_delta <= 0:
            return CompetitionMetricInterpretation(
                bottleneck="Post-install usage is stalled",
                next_best_action="Improve activation and repeat-use value",
                rationale="Installs exist, but reported token usage did not grow.",
                delta=delta,
            )
        return CompetitionMetricInterpretation(
            bottleneck="Competitive growth requires continued measurement",
            next_best_action="Measure the next Agent Index delta and protect momentum",
            rationale="No higher-confidence eligibility, acquisition, or usage bottleneck was detected.",
            delta=delta,
        )


def apply_metrics_decision(
    database: Database,
    mission_id: UUID,
    interpretation: CompetitionMetricInterpretation,
) -> None:
    mission = database.get_mission(mission_id)
    changed = (
        mission.current_bottleneck != interpretation.bottleneck
        or mission.current_best_action != interpretation.next_best_action
    )
    mission.current_bottleneck = interpretation.bottleneck
    mission.current_best_action = interpretation.next_best_action
    database.save_mission(mission)
    if changed:
        database.append_event(
            mission_id,
            "COMPETITION_METRICS_DECISION_UPDATED",
            {
                "bottleneck": interpretation.bottleneck,
                "next_best_action": interpretation.next_best_action,
                "rationale": interpretation.rationale,
                "delta": interpretation.delta.model_dump(mode="json"),
            },
        )
