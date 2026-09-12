from uuid import uuid4

from hackathon_competitor.artifact_graph import ArtifactGraph
from hackathon_competitor.models import Artifact, Mission
from hackathon_competitor.storage import Database


def artifact(mission, task_id, kind):
    return Artifact(
        mission_id=mission.id,
        kind=kind,
        path=f"/{kind}.md",
        content_hash="a" * 64,
        created_by_task_id=task_id,
    )


def test_staleness_propagates_to_all_descendants(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    mission = Mission(title="x", objective="x", workspace_path=str(tmp_path))
    database.save_mission(mission)
    task_id = uuid4()
    source = artifact(mission, task_id, "rules")
    prd = artifact(mission, task_id, "prd")
    pitch = artifact(mission, task_id, "pitch")
    for item in (source, prd, pitch):
        database.save_artifact(item)
    graph = ArtifactGraph(database)
    graph.link(source, prd, "derives_from")
    graph.link(prd, pitch, "claims")

    stale = graph.upstream_changed(source.id)
    assert {item.id for item in stale} == {prd.id, pitch.id}
    assert database.get_artifact(prd.id).stale
    assert database.get_artifact(pitch.id).status == "needs_review"


def test_cross_mission_dependency_is_rejected(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    first = Mission(title="a", objective="a", workspace_path=str(tmp_path))
    second = Mission(title="b", objective="b", workspace_path=str(tmp_path))
    database.save_mission(first)
    database.save_mission(second)
    with __import__("pytest").raises(ValueError, match="cross missions"):
        ArtifactGraph(database).link(
            artifact(first, uuid4(), "a"), artifact(second, uuid4(), "b"), "claims"
        )
