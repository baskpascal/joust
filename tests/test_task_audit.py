from hackathon_competitor.models import Mission, Task
from hackathon_competitor.storage import Database
from hackathon_competitor.task_engine import TaskEngine


def test_audit_events_emit_metrics(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    mission = Mission(title="audit", objective="audit", workspace_path=str(tmp_path))
    database.save_mission(mission)
    engine = TaskEngine(database, retry_base_seconds=0)
    root = Task(mission_id=mission.id, type="root", capability="root")
    child = Task(mission_id=mission.id, type="child", capability="child", dependencies=[root.id])
    engine.add_tasks([root, child])
    engine.refresh_ready(mission.id)
    engine.claim(root.id)
    engine.recover_running(mission.id)
    engine.cancel_from(root.id)
    event_types = [event["event_type"] for event in database.events(mission.id)]
    assert "TASK_FAILED" in event_types
    assert "TASK_CANCELLED" in event_types
    metrics = [item["metric"] for item in database.metrics(mission.id)]
    assert "task_failures" in metrics
    assert "tasks_cancelled" in metrics
