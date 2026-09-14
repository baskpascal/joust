import pytest

from hackathon_competitor.models import AgentIdentity, Mission, MissionState
from hackathon_competitor.storage import MIGRATIONS, Database, transition_mission


def test_migration_persistence_and_append_only_events(tmp_path):
    path = tmp_path / "state.db"
    database = Database(path)
    assert database.migrate() == len(MIGRATIONS)
    mission = Mission(title="Fixture", objective="Win honestly", workspace_path=str(tmp_path))
    database.save_mission(mission)
    database.append_event(mission.id, "MISSION_CREATED", {"title": mission.title})
    transition_mission(database, mission, MissionState.INTAKE)

    reopened = Database(path)
    reopened.migrate()
    loaded = reopened.get_mission(mission.id)
    assert loaded.state == MissionState.INTAKE
    assert [event["event_type"] for event in reopened.events(mission.id)] == [
        "MISSION_CREATED",
        "STATE_CHANGED",
    ]


def test_agent_identity_is_bound_once_per_installation(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    identity = AgentIdentity(agent_id="galahad-hackathon")

    assert database.bind_agent_identity(identity).agent_id == "galahad-hackathon"
    assert database.bind_agent_identity(identity).display_name == "Joust"
    with pytest.raises(ValueError, match="AGENT_ID is immutable"):
        database.bind_agent_identity(AgentIdentity(agent_id="joust"))
