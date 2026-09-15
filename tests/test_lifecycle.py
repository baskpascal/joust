import pytest

from hackathon_competitor.lifecycle import MissionLifecycleService, handle_lifecycle_message
from hackathon_competitor.models import (
    Mission,
    MissionState,
    ProjectMode,
    ProjectTarget,
    Task,
    TaskStatus,
)
from hackathon_competitor.storage import Database
from hackathon_competitor.task_engine import TaskEngine


@pytest.fixture
def setup(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    mission = Mission(title="IBM Bob 2.0", objective="build", workspace_path=str(tmp_path))
    database.save_mission(mission)
    target = ProjectTarget(
        mission_id=mission.id, mode=ProjectMode.LOCAL_ONLY, local_path=str(tmp_path / "rampbot")
    )
    database.save_project_target(target)
    mission.project_target_id = target.id
    database.save_mission(mission)
    return database, mission, target


def test_pause_resume_preserves_target_and_emits_once(setup):
    database, mission, target = setup
    service = MissionLifecycleService(database)
    paused = service.pause(mission.id)
    assert paused.state == MissionState.PAUSED
    assert database.get_project_target_for_mission(mission.id).id == target.id
    assert service.pause(mission.id).state == MissionState.PAUSED
    assert [e["event_type"] for e in database.events(mission.id)].count("MISSION_PAUSED") == 1
    assert service.resume(mission.id).state == MissionState.CREATED


def test_cancel_is_idempotent_and_keeps_project_and_tasks(setup):
    database, mission, target = setup
    task = Task(mission_id=mission.id, type="work", capability="work")
    TaskEngine(database).add_tasks([task])
    cancelled = MissionLifecycleService(database).cancel(mission.id)
    assert cancelled.state == MissionState.CANCELLED
    assert database.get_project_target_for_mission(mission.id).id == target.id
    assert database.get_task(task.id).status == TaskStatus.CANCELLED
    assert MissionLifecycleService(database).cancel(mission.id).state == MissionState.CANCELLED
    assert [e["event_type"] for e in database.events(mission.id)].count("MISSION_CANCELLED") == 1


def test_cancelled_and_paused_missions_cannot_start_competition_cycle(setup):
    database, mission, _target = setup
    service = MissionLifecycleService(database)
    service.cancel(mission.id)
    with pytest.raises(ValueError):
        from hackathon_competitor.compete_loop import CompeteLoop
        CompeteLoop(database).create_cycle(mission.id)


def test_natural_language_question_does_not_cancel(setup):
    database, mission, _target = setup
    service = MissionLifecycleService(database)
    answer = handle_lifecycle_message(service, mission.id, "Can we cancel it?")
    assert "Want me to cancel it?" in answer
    assert database.get_mission(mission.id).state == MissionState.CREATED
    assert "orchestrator" not in answer.lower()


def test_natural_language_command_cancels_without_deleting(setup):
    database, mission, _target = setup
    answer = handle_lifecycle_message(MissionLifecycleService(database), mission.id, "Cancel it.")
    assert "Cancelled IBM Bob 2.0" in answer
    assert database.get_mission(mission.id).state == MissionState.CANCELLED
