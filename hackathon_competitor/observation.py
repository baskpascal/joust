from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from .build_loop import project_environment
from .compete_loop import CompeteLoop
from .github import GitHubTool
from .models import (
    CompeteStage,
    CompetitionObservation,
    CompetitionRuleStatus,
    Evidence,
    MissionState,
    utcnow,
)
from .storage import Database
from .tool_gateway import LocalGitTool, LocalShellTool


class DeploymentObserver(Protocol):
    def health(self, target: str) -> dict[str, Any]: ...


class CompetitionObserver:
    """Collect read-only competition/project signals and advance OBSERVE."""

    def __init__(
        self,
        database: Database,
        *,
        github: GitHubTool | None = None,
        deployment: DeploymentObserver | None = None,
    ):
        self.database = database
        self.github = github
        self.deployment = deployment

    @staticmethod
    def _deadline(spec, mission) -> datetime | None:
        if spec is None:
            return mission.deadline_at
        return (
            spec.final_snapshot_at
            or spec.submission_deadline_at
            or spec.build_deadline_at
            or spec.deadline_at
            or mission.deadline_at
        )

    @staticmethod
    def _state_deadline(state) -> datetime | None:
        if state is None:
            return None
        for key in (
            "FINAL_SNAPSHOT",
            "SUBMISSION_DEADLINE",
            "BUILD_DEADLINE",
            "DEADLINE",
        ):
            if key in state.deadlines:
                return state.deadlines[key]
        return None

    def collect(
        self,
        cycle_id: UUID,
        *,
        now: datetime | None = None,
        score_signals: dict[str, float] | None = None,
    ) -> CompetitionObservation:
        cycle = self.database.get_competition_cycle(cycle_id)
        if cycle.stage != CompeteStage.OBSERVE:
            raise ValueError(f"competition cycle requires OBSERVE, got {cycle.stage.value}")
        mission = self.database.get_mission(cycle.mission_id)
        observed_at = now or utcnow()
        try:
            spec = self.database.get_spec_for_mission(mission.id)
        except KeyError:
            spec = None
        try:
            competition_state = self.database.get_current_competition_state(mission.id)
        except KeyError:
            competition_state = None
        deadline = self._state_deadline(competition_state) or self._deadline(spec, mission)
        deadline_state = "unknown"
        if deadline is not None:
            deadline_state = "expired" if observed_at >= deadline else "upcoming"

        active_rules = (
            list(competition_state.active_rule_ids)
            if competition_state is not None
            else [
                rule.id
                for rule in self.database.list_competition_rules(mission.id)
                if rule.status == CompetitionRuleStatus.ACTIVE
            ]
        )
        observed_scores = dict(competition_state.metrics) if competition_state is not None else {}
        if competition_state is not None:
            for agent_id, snapshot in competition_state.leaderboard.items():
                for metric, value in snapshot.items():
                    if value is not None:
                        observed_scores[f"leaderboard.{agent_id}.{metric}"] = float(value)
        observed_scores.update(score_signals or {})
        findings: list[str] = []
        uncertainties: list[str] = []
        if deadline_state == "expired":
            findings.append("competition deadline has elapsed")
        elif deadline is None:
            uncertainties.append("competition deadline is unknown")
        if not active_rules:
            uncertainties.append("no active versioned competition rules")

        observation = CompetitionObservation(
            mission_id=mission.id,
            cycle_id=cycle.id,
            observed_at=observed_at,
            deadline_at=deadline,
            deadline_state=deadline_state,
            active_rule_ids=active_rules,
            submission_state=(
                "published" if mission.state == MissionState.SUBMITTED else "not_published"
            ),
            score_signals=observed_scores,
            findings=findings,
            uncertainties=uncertainties,
        )

        try:
            target = self.database.get_project_target_for_mission(mission.id)
        except KeyError:
            target = None
            observation.uncertainties.append("mission has no project target")
        if target is not None:
            observation.project_target_id = target.id
            root = Path(target.local_path).resolve()
            observation.repository_exists = (root / ".git").is_dir()
            if observation.repository_exists:
                try:
                    environment = project_environment(target.environment_allowlist)
                    git = LocalGitTool(root, shell=LocalShellTool(root, environment=environment))
                    observation.repository_revision = git.current_revision()
                    observation.repository_dirty = bool(git.changed_files())
                except (RuntimeError, ValueError) as exc:
                    observation.uncertainties.append(f"local Git observation failed: {exc}")
            else:
                observation.uncertainties.append("project target is not a local Git checkout")

            changes = self.database.list_change_sets(mission.id)
            if changes:
                observation.latest_change_status = changes[-1].status
            runs = self.database.list_build_runs(mission.id)
            observation.build_summary = {
                "total": len(runs),
                "passed": sum(run.passed for run in runs),
                "failed": sum(not run.passed for run in runs),
            }
            repository = (
                f"{target.repository_owner}/{target.repository_name}"
                if target.repository_owner and target.repository_name
                else target.repository_url
            )
            ref = target.final_commit_sha or observation.repository_revision
            if self.github is not None and repository and ref:
                try:
                    observation.github_checks = self.github.checks(repository, ref)
                except (OSError, RuntimeError, ValueError) as exc:
                    observation.uncertainties.append(f"GitHub checks observation failed: {exc}")
            if self.deployment is not None and target.deploy_target:
                try:
                    observation.deployment_health = self.deployment.health(target.deploy_target)
                except (OSError, RuntimeError, ValueError) as exc:
                    observation.uncertainties.append(f"deployment observation failed: {exc}")

        return observation

    def capture(
        self,
        cycle_id: UUID,
        *,
        now: datetime | None = None,
        score_signals: dict[str, float] | None = None,
    ) -> CompetitionObservation:
        return self.record(self.collect(cycle_id, now=now, score_signals=score_signals))

    def record(self, observation: CompetitionObservation) -> CompetitionObservation:
        """Persist a successful collection and advance OBSERVE exactly once."""

        cycle = self.database.get_competition_cycle(observation.cycle_id)
        if cycle.stage != CompeteStage.OBSERVE:
            raise ValueError(f"competition cycle requires OBSERVE, got {cycle.stage.value}")
        mission = self.database.get_mission(observation.mission_id)
        self.database.save_competition_observation(observation)
        evidence = Evidence(
            mission_id=mission.id,
            claim=f"Competition observation {observation.id} captured",
            source_type="competition_observation",
            source_uri=None,
            excerpt=json.dumps(
                {
                    "deadline_state": observation.deadline_state,
                    "repository_revision": observation.repository_revision,
                    "repository_dirty": observation.repository_dirty,
                    "latest_change_status": observation.latest_change_status,
                    "build_summary": observation.build_summary,
                    "github_checks": observation.github_checks,
                    "deployment_health": observation.deployment_health,
                    "score_signals": observation.score_signals,
                    "findings": observation.findings,
                    "uncertainties": observation.uncertainties,
                },
                sort_keys=True,
            ),
            confidence=1.0 if not observation.uncertainties else 0.7,
            authority="joust-observation-plane",
            retrieved_at=observation.observed_at,
        )
        self.database.save_evidence(evidence)
        observation.evidence_ids.append(evidence.id)
        self.database.save_competition_observation(observation)
        CompeteLoop(self.database).observe(
            cycle.id,
            self._summary(observation),
            evidence_ids=observation.evidence_ids,
        )
        self.database.append_event(
            mission.id,
            "COMPETITION_OBSERVATION_CAPTURED",
            {
                "observation_id": str(observation.id),
                "cycle_id": str(cycle.id),
                "evidence_ids": [str(item) for item in observation.evidence_ids],
            },
        )
        return observation

    @staticmethod
    def _summary(observation: CompetitionObservation) -> str:
        parts = [f"deadline={observation.deadline_state}"]
        if observation.repository_revision:
            parts.append(f"revision={observation.repository_revision}")
        if observation.latest_change_status:
            parts.append(f"change={observation.latest_change_status}")
        if observation.github_checks:
            parts.append(f"github_checks={len(observation.github_checks)}")
        if observation.deployment_health is not None:
            parts.append("deployment=observed")
        if observation.score_signals:
            parts.append(f"score_signals={len(observation.score_signals)}")
        if observation.uncertainties:
            parts.append(f"uncertainties={len(observation.uncertainties)}")
        return "; ".join(parts)
