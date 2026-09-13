from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID

from .capability import CapabilityRegistry, MissionContext
from .models import EntrantProfile, Mission, MissionState, ProjectTarget
from .storage import Database, transition_mission
from .task_engine import TaskEngine


class MissionOrchestrator:
    def __init__(
        self,
        database: Database,
        artifact_root: str | Path,
        *,
        capability_registry: CapabilityRegistry | None = None,
    ):
        self.database = database
        self.artifact_root = Path(artifact_root)
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self.tasks = TaskEngine(database)
        self.capability_registry = capability_registry

    def create_mission(
        self,
        *,
        title: str,
        objective: str,
        source_inputs: list[str],
        workspace_path: str,
    ) -> Mission:
        mission = Mission(
            title=title,
            objective=objective,
            source_inputs=source_inputs,
            workspace_path=workspace_path,
        )
        self.database.save_mission(mission)
        self.database.append_event(
            mission.id,
            "MISSION_CREATED",
            {"title": mission.title, "source_count": len(source_inputs)},
        )
        self.database.record_metric(mission.id, "mission_started", 1.0)
        return mission

    def resume_mission(self, mission_id: UUID) -> Mission:
        mission = self.database.get_mission(mission_id)
        self.tasks.recover_running(mission.id)
        return self.database.get_mission(mission.id)

    def attach_project_target(self, target: ProjectTarget) -> ProjectTarget:
        mission = self.database.get_mission(target.mission_id)
        if not target.local_path:
            raise ValueError("project target local path cannot be empty")
        self.database.save_project_target(target)
        mission.project_target_id = target.id
        self.database.save_mission(mission)
        self.database.append_event(
            mission.id,
            "PROJECT_TARGET_ATTACHED",
            {
                "project_target_id": str(target.id),
                "repository_url": target.repository_url,
                "mode": target.mode.value,
            },
        )
        return target

    def attach_entrant_profile(self, mission_id: UUID, profile: EntrantProfile) -> EntrantProfile:
        mission = self.database.get_mission(mission_id)
        self.database.save_entrant_profile(profile)
        mission.entrant_profile_id = profile.id
        self.database.save_mission(mission)
        self.database.append_event(
            mission.id,
            "ENTRANT_PROFILE_ATTACHED",
            {
                "entrant_profile_id": str(profile.id),
                "display_name": profile.display_name,
            },
        )
        return profile

    def transition_state(self, mission: Mission, target: MissionState) -> Mission:
        return transition_mission(self.database, mission, target)

    async def dispatch_task(self, task_id: UUID, *, services: dict[str, object] | None = None):
        """Run one registered capability with durable task bookkeeping."""

        if self.capability_registry is None:
            raise LookupError("no capability registry is configured")
        task = self.database.get_task(task_id)
        ready = self.tasks.refresh_ready(task.mission_id)
        if task.id not in {item.id for item in ready}:
            raise ValueError(f"task did not become ready: {task.id}")
        self.tasks.claim(task.id)
        mission = self.database.get_mission(task.mission_id)
        context = MissionContext(
            mission=mission,
            database=self.database,
            artifact_root=self.artifact_root,
            services=services or {},
        )
        try:
            result = await self.capability_registry.dispatch(task, context)
        except Exception as exc:
            self.tasks.fail(task.id, str(exc), retryable=bool(task.inputs.get("retryable", True)))
            raise
        task = self.database.get_task(task.id)
        task.output_artifact_ids = [
            UUID(str(item["id"]))
            for item in result.artifacts
            if isinstance(item, dict) and item.get("id")
        ]
        self.database.save_task(task)
        self.database.append_event(
            task.mission_id,
            "CAPABILITY_RESULT",
            {
                "task_id": str(task.id),
                "capability": task.capability,
                "summary": result.summary,
                "warnings": result.warnings,
            },
        )
        for metric, value in result.metrics.items():
            if isinstance(value, (int, float)):
                self.database.record_metric(task.mission_id, str(metric), float(value))
        self.tasks.succeed(task.id)
        return result

    def run_capability_task(self, task_id: UUID, *, services: dict[str, object] | None = None):
        return asyncio.run(self.dispatch_task(task_id, services=services))

    def pause(self, mission: Mission) -> Mission:
        return self.transition_state(mission, MissionState.PAUSED)

    def cancel(self, mission: Mission) -> Mission:
        return self.transition_state(mission, MissionState.CANCELLED)
