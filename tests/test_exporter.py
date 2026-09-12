import json
import zipfile
from pathlib import Path

from hackathon_competitor.exporter import export_mission_bundle
from hackathon_competitor.orchestrator import MissionOrchestrator
from hackathon_competitor.pipeline import run_vertical_slice
from hackathon_competitor.storage import Database


FIXTURE = Path(__file__).parent / "fixtures/hackathon/official.html"


def test_export_bundle_contains_state_artifacts_and_hash_manifest(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    app = MissionOrchestrator(database, tmp_path / "missions")
    mission = run_vertical_slice(app, str(FIXTURE))
    output = export_mission_bundle(database, mission.id, tmp_path / "exports/mission.zip")
    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
        assert "mission.json" in names
        assert "artifact-manifest.json" in names
        manifest = json.loads(archive.read("artifact-manifest.json"))
        assert len(manifest) == len(database.list_artifacts(mission.id))
        assert all(item["content_hash"] for item in manifest)
        assert any(name.startswith("artifacts/") for name in names)
