from __future__ import annotations

from pathlib import Path
from uuid import UUID

from .models import Mission, MissionState
from .storage import Database, transition_mission
from .task_engine import TaskEngine


class MissionOrchestrator:
    def __init__(self, database: Database, artifact_root: str | Path):
        self.database = database
        self.artifact_root = Path(artifact_root)
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self.tasks = TaskEngine(database)

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
        return mission

    def resume_mission(self, mission_id: UUID) -> Mission:
        mission = self.database.get_mission(mission_id)
        self.tasks.recover_running(mission.id)
        return self.database.get_mission(mission.id)

    def transition_state(self, mission: Mission, target: MissionState) -> Mission:
        return transition_mission(self.database, mission, target)

    def pause(self, mission: Mission) -> Mission:
        return self.transition_state(mission, MissionState.PAUSED)

    def cancel(self, mission: Mission) -> Mission:
        return self.transition_state(mission, MissionState.CANCELLED)
