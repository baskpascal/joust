from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse
from uuid import UUID

from .build_loop import Implementer, ProjectBootstrap, RealBuildLoop
from .capabilities.research import SourceFetcher, parse_source
from .compete_loop import CompeteLoop, CompeteLoopError
from .models import (
    ActionCandidate,
    ActionExecution,
    ActionExecutionStatus,
    ActionResult,
    CompeteStage,
    CompetitionActionType,
    Evidence,
    Mission,
    ProjectTarget,
    utcnow,
)
from .storage import Database


class ActionExecutor(Protocol):
    def execute(
        self,
        mission: Mission,
        target: ProjectTarget | None,
        action: ActionCandidate,
    ) -> ActionResult: ...


class RealBuildActionExecutor:
    """Execute BUILD_PROJECT through the existing real build/repair loop."""

    def __init__(
        self,
        database: Database,
        artifact_root: str | Path,
        implementer: Implementer,
        *,
        github: ProjectBootstrap | None = None,
    ):
        self.database = database
        self.artifact_root = Path(artifact_root)
        self.implementer = implementer
        self.github = github

    def execute(
        self,
        mission: Mission,
        target: ProjectTarget | None,
        action: ActionCandidate,
    ) -> ActionResult:
        if action.action_type != CompetitionActionType.BUILD_PROJECT:
            raise ValueError("real build executor only accepts BUILD_PROJECT actions")
        if target is None:
            raise ValueError("BUILD_PROJECT requires an attached project target")
        specification = action.parameters.get("specification")
        if not isinstance(specification, str) or not specification.strip():
            raise ValueError("BUILD_PROJECT requires a non-empty specification")
        max_repairs = action.parameters.get("max_repairs", 1)
        if not isinstance(max_repairs, int) or isinstance(max_repairs, bool):
            raise TypeError("BUILD_PROJECT max_repairs must be an integer")
        allow_no_changes = action.parameters.get("allow_no_changes", False)
        if not isinstance(allow_no_changes, bool):
            raise TypeError("BUILD_PROJECT allow_no_changes must be a boolean")
        change_set = RealBuildLoop(
            self.database,
            self.artifact_root,
            github=self.github,
        ).run(
            target,
            specification,
            self.implementer,
            max_repairs=max_repairs,
            allow_no_changes=allow_no_changes,
        )
        return ActionResult(
            summary=f"Validated project commit {change_set.commit_sha}",
            details={
                "status": change_set.status,
                "commit_sha": change_set.commit_sha,
                "diff_hash": change_set.diff_hash,
                "files": change_set.files,
            },
            change_set_id=change_set.id,
        )


class RealResearchActionExecutor:
    """Fetch bounded competition sources and persist the observed content."""

    def __init__(
        self,
        database: Database,
        *,
        fetcher: SourceFetcher | None = None,
        max_sources: int = 5,
    ):
        if max_sources < 1:
            raise ValueError("max_sources must be positive")
        self.database = database
        self.fetcher = fetcher or SourceFetcher()
        self.max_sources = max_sources

    def execute(
        self,
        mission: Mission,
        target: ProjectTarget | None,
        action: ActionCandidate,
    ) -> ActionResult:
        if action.action_type != CompetitionActionType.RESEARCH:
            raise ValueError("research executor only accepts RESEARCH actions")
        requested = action.parameters.get("sources", [])
        if not isinstance(requested, list) or any(not isinstance(item, str) for item in requested):
            raise TypeError("RESEARCH sources must be a list of strings")
        try:
            spec = self.database.get_spec_for_mission(mission.id)
        except KeyError:
            spec = None
        candidates = [*requested]
        if spec is not None:
            if spec.canonical_url:
                candidates.append(spec.canonical_url)
            candidates.extend(spec.rule_sources)

        sources: list[str] = []
        for candidate in candidates:
            uri = candidate.strip()
            parsed = urlparse(uri)
            supported = parsed.scheme in {"http", "https"} or (
                parsed.scheme in {"", "file"} and Path(parsed.path or uri).is_absolute()
            )
            if supported and uri not in sources:
                sources.append(uri)
            if len(sources) == self.max_sources:
                break
        if not sources:
            raise ValueError("RESEARCH has no supported competition source")

        evidence_ids: list[UUID] = []
        captured: list[str] = []
        failures: list[str] = []
        for uri in sources:
            try:
                content = self.fetcher.fetch(uri)
                parsed = parse_source(content, uri, "official", "competition_research")
                excerpt = parsed.text.strip()
                if not excerpt:
                    raise ValueError("source contained no readable text")
                evidence = Evidence(
                    mission_id=mission.id,
                    claim=f"Competition research source captured for: {action.name}",
                    source_type="competition_research",
                    source_uri=uri,
                    excerpt=excerpt[:1000],
                    confidence=0.9,
                    authority="official-source-snapshot",
                )
                self.database.save_evidence(evidence)
                evidence_ids.append(evidence.id)
                captured.append(uri)
            except (OSError, RuntimeError, UnicodeError, ValueError) as exc:
                failures.append(f"{uri}: {exc}")
        if not evidence_ids:
            raise RuntimeError("RESEARCH produced no verifiable source evidence")
        return ActionResult(
            summary=f"Captured {len(evidence_ids)} competition research source(s)",
            details={"sources": captured, "failures": failures},
            evidence_ids=evidence_ids,
        )


class CompetitionActionDispatcher:
    """Persist and dispatch the action selected by a competition cycle."""

    def __init__(
        self,
        database: Database,
        executors: Mapping[CompetitionActionType, ActionExecutor],
    ):
        self.database = database
        self.executors = dict(executors)

    def execute_selected(self, cycle_id: UUID) -> ActionExecution:
        cycle = self.database.get_competition_cycle(cycle_id)
        existing = [
            item
            for item in self.database.list_action_executions(cycle.mission_id)
            if item.cycle_id == cycle.id
        ]
        if existing:
            previous = existing[-1]
            if previous.status != ActionExecutionStatus.RUNNING:
                return previous
            previous.status = ActionExecutionStatus.FAILED
            previous.error = "action process ended before a durable result was recorded"
            previous.finished_at = utcnow()
            self.database.save_action_execution(previous)
            CompeteLoop(self.database).record_execution(
                cycle.id,
                result=f"{previous.action.name} was interrupted before completion",
                succeeded=False,
            )
            self.database.append_event(
                cycle.mission_id,
                "COMPETITION_ACTION_INTERRUPTED",
                {"execution_id": str(previous.id), "cycle_id": str(cycle.id)},
            )
            return previous
        if cycle.stage != CompeteStage.EXECUTE:
            raise CompeteLoopError(f"competition cycle requires EXECUTE, got {cycle.stage.value}")
        if cycle.selected_action is None:
            raise CompeteLoopError("competition cycle has no selected action")
        action = cycle.selected_action
        executor = self.executors.get(action.action_type)
        if executor is None:
            raise CompeteLoopError(f"no executor registered for {action.action_type.value}")
        mission = self.database.get_mission(cycle.mission_id)
        try:
            target = self.database.get_project_target_for_mission(mission.id)
        except KeyError:
            target = None
        execution = ActionExecution(
            mission_id=mission.id,
            cycle_id=cycle.id,
            action=action,
        )
        self.database.save_action_execution(execution)
        self.database.append_event(
            mission.id,
            "COMPETITION_ACTION_STARTED",
            {
                "execution_id": str(execution.id),
                "cycle_id": str(cycle.id),
                "action_type": action.action_type.value,
                "action_name": action.name,
            },
        )
        try:
            result = executor.execute(mission, target, action)
        except (RuntimeError, TypeError, ValueError, TimeoutError) as exc:
            execution.status = ActionExecutionStatus.FAILED
            execution.error = str(exc)
            execution.finished_at = utcnow()
            self.database.save_action_execution(execution)
            CompeteLoop(self.database).record_execution(
                cycle.id,
                result=f"{action.name} failed: {exc}",
                succeeded=False,
            )
            self.database.append_event(
                mission.id,
                "COMPETITION_ACTION_FAILED",
                {"execution_id": str(execution.id), "error": str(exc)},
            )
            return execution

        evidence = Evidence(
            mission_id=mission.id,
            claim=f"Competition action completed: {action.name}",
            source_type=(
                "git_commit" if result.change_set_id is not None else "competition_action"
            ),
            source_uri=target.repository_url if target is not None else None,
            excerpt=json.dumps(result.model_dump(mode="json"), sort_keys=True),
            confidence=1.0,
            authority="joust-execution-plane",
        )
        self.database.save_evidence(evidence)
        result.evidence_ids.append(evidence.id)
        execution.result = result
        execution.status = ActionExecutionStatus.SUCCEEDED
        execution.finished_at = utcnow()
        self.database.save_action_execution(execution)
        CompeteLoop(self.database).record_execution(
            cycle.id,
            result=result.summary,
            succeeded=True,
        )
        self.database.append_event(
            mission.id,
            "COMPETITION_ACTION_SUCCEEDED",
            {
                "execution_id": str(execution.id),
                "evidence_ids": [str(item) for item in result.evidence_ids],
            },
        )
        return execution
