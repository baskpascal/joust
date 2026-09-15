from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from .ai import ModelUnavailable
from .competition_actions import ActionExecutor
from .models import (
    ActionCandidate,
    ActionExecution,
    ActionExecutionStatus,
    ActionResult,
    AdaptationPlan,
    AssessmentPlan,
    CompetitionActionType,
    CompetitionCycle,
    CompetitionObservation,
    Measurement,
    Mission,
    ProjectTarget,
)
from .storage import Database
from .tool_gateway import LocalShellTool


class TextReasoner(Protocol):
    def complete(self, prompt: str) -> str: ...


def _current_strategy(database: Database, mission: Mission) -> dict | None:
    """What the mission is actually trying to win with, right now.

    Without this, a planner reasons only from the project's current state —
    its README, its passing or failing checks — and never from *why* that
    project exists. A strategy pivot (`ai_mission.redirect`) changes which
    candidate is active; a planner that never reads that field can propose
    actions that are locally sensible and globally incoherent with what the
    mission just decided to pursue instead.
    """

    decisions = [
        item
        for item in database.list_ai_decisions(mission.id)
        if item.decision_type in {"strategy_selection", "strategy_reassessment"}
    ]
    if not decisions:
        return None
    selected_id = decisions[-1].selected_option
    for candidate in database.list_strategy_candidates(mission.id):
        if str(candidate.id) == selected_id:
            return {
                "product_thesis": candidate.product_thesis,
                "target_user": candidate.target_user,
                "winning_mechanism": candidate.winning_mechanism,
                "risks": candidate.risks,
            }
    return None


_HTTP_ERROR_PATTERN = re.compile(r"\bHTTP\s+(\d{3})\b")


def _classify_transport_failure(text: str) -> tuple[str, str] | None:
    """Detect an HTTP failure the `hermes` CLI printed instead of raising.

    A 401 from the API is not "the model returned nothing" — it never asked
    a model anything — but the CLI's own error text (`HTTP 401: {"detail":
    ...}`) still contains a syntactically valid JSON object, so a bare
    `json_object()` scan happily parses it as if it were an answer. This has
    to be caught before that scan ever runs, at the one place that actually
    knows this text came from a failed request rather than a completion.
    Returns `(code, detail)` for a recognised failure, `None` for ordinary
    model output.
    """

    match = _HTTP_ERROR_PATTERN.search(text[:200])
    if match is None:
        return None
    status = int(match.group(1))
    detail = text.strip()[:400]
    if status in (401, 403):
        return "MODEL_AUTHENTICATION_FAILED", detail
    if status == 429:
        return "MODEL_RATE_LIMITED", detail
    if status >= 500:
        return "MODEL_PROVIDER_UNAVAILABLE", detail
    return None


class HermesOneShotReasoner:
    """Invoke the configured Hermes model and return its final response."""

    def __init__(
        self,
        workdir: str | Path,
        *,
        executable: str = "/opt/hermes/bin/hermes",
        model: str | None = None,
        provider: str | None = None,
        reasoning: str | None = None,
        environment: dict[str, str] | None = None,
        timeout_seconds: float = 60,
    ):
        self.workdir = Path(workdir).resolve()
        self.executable = executable
        self.environment = dict(environment) if environment is not None else os.environ.copy()
        self.model = model or self.environment.get(
            "JOUST_PLANNER_MODEL", "anthropic/claude-sonnet-5"
        )
        self.provider = provider or self.environment.get("JOUST_PLANNER_PROVIDER", "plow")
        self.reasoning = reasoning or self.environment.get("JOUST_PLANNER_REASONING", "minimal")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.timeout_seconds = timeout_seconds

    def complete(self, prompt: str) -> str:
        argv = [
            self.executable,
            "--in",
            str(self.workdir),
            "--safe-mode",
            "--ignore-rules",
            "-t",
            "",
        ]
        argv.extend(["--provider", self.provider, "--model", self.model])
        argv.extend(["--reasoning", self.reasoning])
        argv.extend(["-z", prompt])
        try:
            text = LocalShellTool(self.workdir, environment=self.environment).run(
                argv,
                timeout_seconds=self.timeout_seconds,
            )
        except TimeoutError as error:
            raise ModelUnavailable(
                "MODEL_TIMEOUT", f"no answer in {self.timeout_seconds:.0f}s"
            ) from error
        failure = _classify_transport_failure(text)
        if failure is not None:
            code, detail = failure
            raise ModelUnavailable(code, detail)
        return text


def _json_object(text: str) -> dict:
    decoder = json.JSONDecoder()
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError("Hermes planner did not return a JSON object")


class HermesCompetitionPlanner:
    """Ask Hermes for bounded action candidates, then validate every field."""

    def __init__(
        self,
        database: Database,
        reasoner: TextReasoner,
        *,
        allowed_action_types: set[CompetitionActionType],
        max_repairs: int = 1,
    ):
        if max_repairs < 0:
            raise ValueError("max_repairs cannot be negative")
        self.database = database
        self.reasoner = reasoner
        self.allowed_action_types = set(allowed_action_types)
        self.max_repairs = max_repairs

    def assess(
        self,
        mission: Mission,
        observation: CompetitionObservation,
    ) -> AssessmentPlan:
        try:
            spec_model = self.database.get_spec_for_mission(mission.id)
            spec = {
                "name": spec_model.name,
                "competition_type": spec_model.competition_type.value,
                "final_snapshot_at": (
                    spec_model.final_snapshot_at.isoformat()
                    if spec_model.final_snapshot_at
                    else None
                ),
                "scoring_rules": spec_model.scoring_rules,
                "mandatory_integrations": spec_model.mandatory_integrations,
                "prohibited_actions": spec_model.prohibited_actions,
                "uncertainty": spec_model.uncertainty,
            }
        except KeyError:
            spec = None
        strategy = _current_strategy(self.database, mission)
        try:
            target = self.database.get_project_target_for_mission(mission.id)
            target_payload = {
                "mode": target.mode.value,
                "repository": target.repository_url,
                "default_branch": target.default_branch,
                "working_branch": target.working_branch,
                "language": target.language,
                "framework": target.framework,
                "deployment_requirement": target.deployment_requirement,
                "deploy_target": target.deploy_target,
                "has_install_command": bool(target.install_commands),
                "has_test_command": bool(target.test_commands),
                "has_build_command": bool(target.build_commands),
                "has_lint_command": bool(target.lint_commands),
            }
            readme = Path(target.local_path) / "README.md"
            project_readme = (
                readme.read_text(encoding="utf-8")[:1500] if readme.is_file() else "unavailable"
            )
        except KeyError:
            target_payload = None
            project_readme = "unavailable"
        artifacts = [
            item
            for item in self.database.list_artifacts(mission.id)
            if item.kind == "implementation_plan" and not item.stale
        ]
        implementation_plan = None
        if artifacts:
            path = Path(artifacts[-1].path)
            if path.is_file():
                implementation_plan = path.read_text(encoding="utf-8")[:6000]
        schema = {
            "bottleneck": "short concrete bottleneck",
            "candidates": [
                {
                    "name": "short action name",
                    "description": "what changes and why",
                    "action_type": "one of the allowed values",
                    "parameters": {
                        "specification": "required only for BUILD_PROJECT",
                        "max_repairs": self.max_repairs,
                        "allow_no_changes": "true only for verification-only BUILD_PROJECT",
                        "sources": ["required official URLs only for RESEARCH"],
                    },
                    "expected_outcome_improvement": 0.0,
                    "time_cost": 1.0,
                    "technical_risk": 0.0,
                    "regression_probability": 0.0,
                }
            ],
        }
        mission_payload = {
            "title": mission.title,
            "objective": mission.objective,
            "deadline_at": mission.deadline_at.isoformat() if mission.deadline_at else None,
            "current_bottleneck": mission.current_bottleneck,
            "current_best_action": mission.current_best_action,
            "mission_score": mission.mission_score,
            "confidence": mission.confidence,
            "unresolved_questions": mission.unresolved_questions,
        }
        observation_payload = {
            "deadline_state": observation.deadline_state,
            "repository_exists": observation.repository_exists,
            "repository_revision": observation.repository_revision,
            "repository_dirty": observation.repository_dirty,
            "latest_change_status": observation.latest_change_status,
            "build_summary": observation.build_summary,
            "github_checks": observation.github_checks,
            "deployment_health": observation.deployment_health,
            "submission_state": observation.submission_state,
            "score_signals": observation.score_signals,
            "findings": observation.findings,
            "uncertainties": observation.uncertainties,
        }
        context = {
            "allowed_action_types": sorted(item.value for item in self.allowed_action_types),
            "mission": mission_payload,
            "competition": spec,
            "active_strategy": strategy,
            "project": target_payload,
            "project_readme": project_readme,
            "observation": observation_payload,
            "implementation_plan": implementation_plan or "unavailable",
            "recent_cycles": [
                {
                    "sequence": cycle.sequence,
                    "action": cycle.selected_action.name if cycle.selected_action else None,
                    "action_type": (
                        cycle.selected_action.action_type.value if cycle.selected_action else None
                    ),
                    "execution_result": cycle.execution_result,
                    "verified": cycle.verified,
                    "measured_delta": cycle.measured_delta,
                }
                for cycle in self.database.list_competition_cycles(mission.id)[-3:]
                if cycle.completed_at is not None
            ],
        }
        prompt = (
            "You are Joust's competition planner. Select 1 or 2 concrete candidate "
            "actions that improve the probability of winning. Return exactly one JSON "
            "object and no markdown. Do not choose actions outside allowed_action_types. "
            "BUILD_PROJECT must include a complete implementation specification; RESEARCH "
            "must identify official source URLs; CUSTOM is only a deliberate no-op/observe "
            "action and must not claim research or project mutation. Do not repeat a "
            "successful zero-delta action unless the observation changed. If active_strategy "
            "is present, every candidate must serve it; a candidate that would only make "
            "sense for a different product thesis is wrong regardless of how well it fixes "
            "what the project currently is. Never invent "
            "API endpoints, credentials, telemetry, or substitute clients; preserve and "
            "use official integrations already present in the project. Values "
            "for improvement, time, risk, and probability must be non-negative numbers; "
            "time_cost must be greater than zero.\n\n"
            f"response_schema={json.dumps(schema, sort_keys=True)}\n"
            f"context={json.dumps(context, sort_keys=True)}"
        )
        try:
            response = self.reasoner.complete(prompt)
        except TimeoutError as exc:
            return self._timeout_fallback(mission, observation, target_payload, exc)
        try:
            plan = AssessmentPlan.model_validate(_json_object(response))
        except ValidationError as exc:
            raise ValueError(f"Hermes planner returned an invalid assessment: {exc}") from exc
        if not 1 <= len(plan.candidates) <= 2:
            raise ValueError("Hermes planner must return one or two candidates")
        for candidate in plan.candidates:
            if candidate.action_type not in self.allowed_action_types:
                raise ValueError(
                    f"Hermes planner selected unsupported action: {candidate.action_type.value}"
                )
            if candidate.action_type == CompetitionActionType.BUILD_PROJECT:
                specification = candidate.parameters.get("specification")
                if not isinstance(specification, str) or not specification.strip():
                    raise ValueError("Hermes BUILD_PROJECT action omitted its specification")
                requested = candidate.parameters.get("max_repairs", self.max_repairs)
                if not isinstance(requested, int) or isinstance(requested, bool):
                    raise TypeError("Hermes BUILD_PROJECT max_repairs must be an integer")
                candidate.parameters["max_repairs"] = min(max(requested, 0), self.max_repairs)
                allow_no_changes = candidate.parameters.get("allow_no_changes", False)
                if not isinstance(allow_no_changes, bool):
                    raise TypeError("Hermes BUILD_PROJECT allow_no_changes must be a boolean")
            if candidate.action_type == CompetitionActionType.RESEARCH:
                sources = candidate.parameters.get("sources")
                if (
                    not isinstance(sources, list)
                    or not sources
                    or any(not isinstance(item, str) or not item.strip() for item in sources)
                ):
                    raise ValueError("Hermes RESEARCH action omitted official source URLs")
        return plan

    def _timeout_fallback(
        self,
        mission: Mission,
        observation: CompetitionObservation,
        target_payload: dict | None,
        error: TimeoutError,
    ) -> AssessmentPlan:
        self.database.append_event(
            mission.id,
            "COMPETITION_PLANNER_FALLBACK",
            {"reason": str(error), "policy": "deterministic_safe_action"},
        )
        if target_payload is not None and observation.build_summary.get("total", 0) == 0:
            action = ActionCandidate(
                name="Run and repair the local verification pipeline",
                description=(
                    "Establish real build and test evidence before publication or deployment"
                ),
                action_type=CompetitionActionType.BUILD_PROJECT,
                parameters={
                    "specification": (
                        "Inspect the existing project and preserve its architecture and official "
                        "integrations. Run the target's configured install, test, lint, and build "
                        "commands. If a configured verification command fails, diagnose it and "
                        "apply only the smallest local repair needed, then rerun verification. "
                        "Do not invent APIs, credentials, telemetry, endpoints, or external "
                        "state. Do not push, deploy, publish, or submit. If the project is already "
                        "correct, make no feature changes and report the verified result."
                    ),
                    "max_repairs": self.max_repairs,
                    "allow_no_changes": True,
                },
                expected_outcome_improvement=0.2,
                time_cost=2.0,
                technical_risk=0.1,
                regression_probability=0.05,
            )
            bottleneck = "No durable build or test result exists for the target project"
        else:
            action = ActionCandidate(
                name="Wait for a changed observation",
                description="Preserve state without claiming research or project mutation",
                action_type=CompetitionActionType.CUSTOM,
                expected_outcome_improvement=0.01,
                time_cost=1.0,
                technical_risk=0.0,
                regression_probability=0.0,
            )
            bottleneck = "Hermes planning timed out and no deterministic build gap was found"
        return AssessmentPlan(bottleneck=bottleneck, candidates=[action])

    def adapt(
        self,
        mission: Mission,
        cycle: CompetitionCycle,
        execution: ActionExecution,
        measurement: Measurement,
    ) -> AdaptationPlan:
        succeeded = execution.status == ActionExecutionStatus.SUCCEEDED
        if succeeded and execution.action.action_type == CompetitionActionType.RESEARCH:
            next_bottleneck = (
                "Research evidence captured; compare it with active rules and choose "
                "a non-duplicate competitive action"
            )
        elif succeeded and execution.action.action_type == CompetitionActionType.CUSTOM:
            next_bottleneck = "No-op complete; wait for a changed observation before repeating"
        elif succeeded:
            next_bottleneck = "Observe new competition and project signals"
        else:
            next_bottleneck = execution.error or "Reassess failed competition action"
        return AdaptationPlan(
            next_bottleneck=next_bottleneck,
            next_best_action="Run the next evidence-backed competition iteration",
            mission_score=measurement.after,
            confidence=0.8 if succeeded else 0.4,
        )


class ReadinessMeasurer:
    """Measure internal project readiness without inventing leaderboard score."""

    def measure(
        self,
        mission: Mission,
        observation: CompetitionObservation,
        execution: ActionExecution,
    ) -> Measurement:
        before = mission.mission_score or 0.0
        after = before
        metric = "project_readiness"
        if "mission_score" in observation.score_signals:
            after = observation.score_signals["mission_score"]
            metric = "observed_mission_score"
        elif (
            execution.status == ActionExecutionStatus.SUCCEEDED
            and execution.action.action_type == CompetitionActionType.BUILD_PROJECT
        ):
            after = max(before, 1.0)
        return Measurement(before=before, after=after, metric=metric)


class ObservationOnlyExecutor(ActionExecutor):
    """Record a deliberate no-mutation action without pretending to build."""

    def execute(
        self,
        mission: Mission,
        target: ProjectTarget | None,
        action: ActionCandidate,
    ) -> ActionResult:
        return ActionResult(
            summary="Observation-only action completed; no project mutation was claimed",
            details={"action": action.name, "project_target": str(target.id) if target else None},
        )
