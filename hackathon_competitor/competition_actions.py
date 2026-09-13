from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol
from uuid import UUID

from .build_loop import Implementer, ProjectBootstrap, RealBuildLoop
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
        change_set = RealBuildLoop(
            self.database,
            self.artifact_root,
            github=self.github,
        ).run(
            target,
            specification,
            self.implementer,
            max_repairs=max_repairs,
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
            return existing[-1]
        if cycle.stage != CompeteStage.EXECUTE:
            raise CompeteLoopError(
                f"competition cycle requires EXECUTE, got {cycle.stage.value}"
            )
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
                "git_commit"
                if result.change_set_id is not None
                else "competition_action"
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
