import asyncio
from pathlib import Path

import pytest

from hackathon_competitor.capability import CapabilityRegistry, MissionContext
from hackathon_competitor.models import CapabilityResult, Mission, Task
from hackathon_competitor.registry import INITIAL_CAPABILITIES, default_registry
from hackathon_competitor.storage import Database


class ExampleCapability:
    name = "example"

    def can_handle(self, task):
        return task.capability == self.name

    async def execute(self, task, context):
        return CapabilityResult(summary=context.services["summary"])


def test_capability_registry_dispatches_structured_results(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    mission = Mission(title="Test", objective="Test", workspace_path=str(tmp_path))
    database.save_mission(mission)
    task = Task(mission_id=mission.id, type="test", capability="example")
    context = MissionContext(
        mission=mission,
        database=database,
        artifact_root=Path(tmp_path),
        services={"summary": "done"},
    )
    registry = CapabilityRegistry([ExampleCapability()])
    result = asyncio.run(registry.dispatch(task, context))
    assert result == CapabilityResult(summary="done")
    assert registry.names() == ("example",)


def test_capability_registry_rejects_duplicates_and_unknown_names():
    registry = CapabilityRegistry([ExampleCapability()])
    with pytest.raises(ValueError, match="already registered"):
        registry.register(ExampleCapability())
    with pytest.raises(LookupError, match="not registered"):
        registry.get("missing")


def test_default_registry_exposes_the_sdd_capability_surface(tmp_path):
    registry = default_registry()
    names = {name for group in INITIAL_CAPABILITIES.values() for name in group}
    assert set(registry.names()) == names
    database = Database(tmp_path / "state.db")
    database.migrate()
    mission = Mission(title="Test", objective="Test", workspace_path=str(tmp_path))
    database.save_mission(mission)
    task = Task(mission_id=mission.id, type="test", capability="web_research")
    context = MissionContext(mission, database, Path(tmp_path), {})
    with pytest.raises(LookupError, match="no handler"):
        asyncio.run(registry.dispatch(task, context))
