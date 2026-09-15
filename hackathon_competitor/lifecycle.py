"""The single public lifecycle boundary for user-controlled missions."""

from __future__ import annotations

from uuid import UUID
from pathlib import Path

from .models import Mission, MissionState, MissionStatus
from .state_machine import require_transition
from .storage import Database
from .task_engine import TaskEngine


class MissionLifecycleService:
    """Pause, resume, and cancel without touching the project itself."""

    def __init__(self, database: Database, tasks: TaskEngine | None = None):
        self.database = database
        self.tasks = tasks or TaskEngine(database)

    def _set(self, mission: Mission, target: MissionState, event: str) -> Mission:
        require_transition(mission.state, target)
        previous = mission.state
        mission.state = target
        self.database.save_mission(mission)
        self.database.append_event(
            mission.id, event, {"from": previous.value, "to": target.value}
        )
        return self.database.get_mission(mission.id)

    def pause(self, mission_id: UUID) -> Mission:
        mission = self.database.get_mission(mission_id)
        if mission.state == MissionState.PAUSED:
            return mission
        if mission.state == MissionState.CANCELLED:
            return mission
        mission.paused_from_state = mission.state
        return self._set(mission, MissionState.PAUSED, "MISSION_PAUSED")

    def resume(self, mission_id: UUID) -> Mission:
        mission = self.database.get_mission(mission_id)
        if mission.state != MissionState.PAUSED:
            if mission.state == MissionState.CANCELLED:
                return mission
            self.tasks.recover_running(mission.id)
            return self.database.get_mission(mission.id)
        target = mission.paused_from_state or MissionState.CREATED
        mission.paused_from_state = None
        resumed = self._set(mission, target, "MISSION_RESUMED")
        self.tasks.recover_running(resumed.id)
        return self.database.get_mission(resumed.id)

    def cancel(self, mission_id: UUID) -> Mission:
        mission = self.database.get_mission(mission_id)
        if mission.state == MissionState.CANCELLED:
            return mission
        if mission.state == MissionState.POSTMORTEM:
            return mission
        cancelled = self._set(mission, MissionState.CANCELLED, "MISSION_CANCELLED")
        cancelled.status = MissionStatus.STOPPED_BY_USER
        self.database.save_mission(cancelled)
        self.tasks.cancel_mission(cancelled.id)
        return self.database.get_mission(cancelled.id)


def handle_lifecycle_message(
    service: MissionLifecycleService, mission_id: UUID, message: str
) -> str | None:
    """Translate the small set of lifecycle phrases used by Plow Chat.

    Questions describe the effect and ask for confirmation; imperative
    lifecycle phrases execute through the same service used by the CLI.
    """

    normalized = " ".join(message.lower().strip().split())
    mission = service.database.get_mission(mission_id)
    target = (
        service.database.get_project_target_for_mission(mission.id)
        if mission.project_target_id
        else None
    )
    project = (
        target.repository_name
        if target and target.repository_name
        else Path(target.local_path).name
        if target
        else "the project"
    )
    question = normalized.endswith("?") or normalized.startswith(
        ("can we ", "could we ", "should we ", "is it possible")
    )
    cancel = any(phrase in normalized for phrase in ("cancel", "quit this competition"))
    pause = any(phrase in normalized for phrase in ("pause", "stop working", "hold this"))
    resume = any(phrase in normalized for phrase in ("resume", "continue", "carry on"))
    if "delete" in normalized or "remove everything" in normalized:
        return "What exactly should I delete? Deletion is separate and requires confirmation."
    if cancel and question:
        return (
            f"Yes. Cancelling will stop work on {mission.title}, but I'll keep {project}, "
            "its files, and the mission history. Want me to cancel it?"
        )
    if cancel:
        service.cancel(mission_id)
        suffix = f"\nProject: {target.repository_url}" if target and target.repository_url else ""
        return f"Cancelled {mission.title}.\n\n{project} and its files were kept.\nI won't do any more work on this competition.{suffix}"
    if pause:
        service.pause(mission_id)
        return f"Paused {mission.title}.\n\n{project} and the mission history are still here.\nSay 'resume' whenever you want me to continue."
    if resume:
        service.resume(mission_id)
        return f"Resumed {mission.title}. I'll continue working on it."
    return None
