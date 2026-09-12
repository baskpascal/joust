from uuid import uuid4

import pytest

from hackathon_competitor.models import Mission, Task, TaskStatus
from hackathon_competitor.storage import Database
from hackathon_competitor.task_engine import DependencyError, TaskEngine


def setup_engine(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    mission = Mission(title="x", objective="x", workspace_path=str(tmp_path))
    database.save_mission(mission)
    return database, mission, TaskEngine(database, retry_base_seconds=0)


def test_dependencies_gate_readiness_and_success(tmp_path):
    database, mission, engine = setup_engine(tmp_path)
    first = Task(mission_id=mission.id, type="first", capability="first")
    second = Task(
        mission_id=mission.id,
        type="second",
        capability="second",
        dependencies=[first.id],
    )
    engine.add_tasks([second, first])
    assert [task.id for task in engine.refresh_ready(mission.id)] == [first.id]
    engine.claim(first.id)
    engine.succeed(first.id)
    assert [task.id for task in engine.refresh_ready(mission.id)] == [second.id]
    assert database.get_task(first.id).status == TaskStatus.SUCCEEDED


def test_cycle_is_rejected_before_persistence(tmp_path):
    database, mission, engine = setup_engine(tmp_path)
    first_id, second_id = uuid4(), uuid4()
    first = Task(
        id=first_id,
        mission_id=mission.id,
        type="first",
        capability="first",
        dependencies=[second_id],
    )
    second = Task(
        id=second_id,
        mission_id=mission.id,
        type="second",
        capability="second",
        dependencies=[first_id],
    )
    with pytest.raises(DependencyError, match="cycle"):
        engine.add_tasks([first, second])
    assert database.list_tasks(mission.id) == []


def test_retry_limit_and_crash_recovery_are_persisted(tmp_path):
    database, mission, engine = setup_engine(tmp_path)
    task = Task(mission_id=mission.id, type="work", capability="work", max_retries=1)
    engine.add_tasks([task])
    engine.refresh_ready(mission.id)
    engine.claim(task.id)
    recovered = engine.recover_running(mission.id)
    assert recovered[0].status == TaskStatus.FAILED_RETRYABLE
    engine.refresh_ready(mission.id)
    engine.claim(task.id)
    failed = engine.fail(task.id, "still broken", retryable=True)
    assert failed.status == TaskStatus.FAILED_PERMANENT


def test_duplicate_task_id_is_rejected(tmp_path):
    database, mission, engine = setup_engine(tmp_path)
    task = Task(mission_id=mission.id, type="work", capability="work")
    engine.add_tasks([task])
    with pytest.raises(DependencyError, match="already exist"):
        engine.add_tasks([task])


def test_retry_backoff_prevents_immediate_hot_loop(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    mission = Mission(title="x", objective="x", workspace_path=str(tmp_path))
    database.save_mission(mission)
    engine = TaskEngine(database, retry_base_seconds=60)
    task = Task(mission_id=mission.id, type="work", capability="work")
    engine.add_tasks([task])
    engine.refresh_ready(mission.id)
    engine.claim(task.id)
    failed = engine.fail(task.id, "transient", retryable=True)
    assert failed.retry_after is not None
    assert engine.refresh_ready(mission.id) == []
