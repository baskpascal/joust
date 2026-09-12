import asyncio

import pytest

from hackathon_competitor.capability import CapabilityRegistry, MissionContext, service_capability
from hackathon_competitor.models import CapabilityResult, Mission, Task, TaskStatus
from hackathon_competitor.orchestrator import MissionOrchestrator
from hackathon_competitor.storage import Database


def test_orchestrator_dispatch_persists_structured_result_and_metrics(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    registry = CapabilityRegistry([service_capability("demo")])
    app = MissionOrchestrator(database, tmp_path / "missions", capability_registry=registry)
    mission = Mission(title="Dispatch", objective="test", workspace_path=str(tmp_path))
    database.save_mission(mission)
    task = Task(mission_id=mission.id, type="demo", capability="demo")
    app.tasks.add_tasks([task])

    async def handler(task, ctx: MissionContext):
        return CapabilityResult(summary="finished", metrics={"dispatch_calls": 1})

    result = asyncio.run(
        app.dispatch_task(
            task.id,
            services={"capability_handlers": {"demo": handler}},
        )
    )
    assert result.summary == "finished"
    assert database.get_task(task.id).status == TaskStatus.SUCCEEDED
    assert any(event["event_type"] == "CAPABILITY_RESULT" for event in database.events(mission.id))
    assert any(
        metric["metric"] == "dispatch_calls" and metric["value"] == 1
        for metric in database.metrics(mission.id)
    )


def test_orchestrator_dispatch_marks_provider_failure_retryable(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    registry = CapabilityRegistry([service_capability("demo")])
    app = MissionOrchestrator(database, tmp_path / "missions", capability_registry=registry)
    mission = Mission(title="Dispatch", objective="test", workspace_path=str(tmp_path))
    database.save_mission(mission)
    task = Task(mission_id=mission.id, type="demo", capability="demo")
    app.tasks.add_tasks([task])
    with pytest.raises(LookupError, match="no handler"):
        asyncio.run(app.dispatch_task(task.id))
    assert database.get_task(task.id).status == TaskStatus.FAILED_RETRYABLE
