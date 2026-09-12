from __future__ import annotations

import hashlib
from uuid import UUID

from .models import Artifact, CompetitionMemory, MissionState, Task
from .orchestrator import MissionOrchestrator


def record_postmortem(
    orchestrator: MissionOrchestrator,
    mission_id: UUID,
    *,
    outcome: str,
    lessons: list[str],
) -> Artifact:
    """Record an explicit outcome without claiming that an external submission occurred."""

    mission = orchestrator.database.get_mission(mission_id)
    allowed = {MissionState.READY_FOR_SUBMISSION, MissionState.SUBMITTED, MissionState.BLOCKED}
    if mission.state not in allowed:
        raise ValueError(f"postmortem is not valid in mission state {mission.state.value}")
    if not outcome.strip():
        raise ValueError("postmortem outcome cannot be empty")
    task = Task(
        mission_id=mission.id,
        type="postmortem",
        capability="postmortem",
        priority=1,
        depth_level=2,
    )
    orchestrator.tasks.add_tasks([task])
    orchestrator.tasks.refresh_ready(mission.id)
    orchestrator.tasks.claim(task.id)
    content = (
        f"# Mission postmortem\n\n## Outcome\n\n{outcome.strip()}\n\n"
        "## Lessons\n\n"
        + "\n".join(f"- {lesson}" for lesson in lessons)
        + "\n\nExternal submission status: not inferred from this record.\n"
    )
    path = orchestrator.artifact_root / str(mission.id) / "artifacts" / "POSTMORTEM.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    artifact = Artifact(
        mission_id=mission.id,
        kind="postmortem",
        path=str(path),
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        created_by_task_id=task.id,
    )
    orchestrator.database.save_artifact(artifact)
    orchestrator.database.append_event(
        mission.id,
        "ARTIFACT_CREATED",
        {"artifact_id": str(artifact.id), "kind": artifact.kind},
    )
    orchestrator.tasks.succeed(task.id)
    for lesson in lessons:
        orchestrator.database.save_competition_memory(
            CompetitionMemory(
                mission_id=mission.id,
                category="postmortem_lesson",
                content=lesson,
                confidence=0.65,
            )
        )
    return artifact
