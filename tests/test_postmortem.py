from pathlib import Path

import pytest

from hackathon_competitor.models import MissionState
from hackathon_competitor.orchestrator import MissionOrchestrator
from hackathon_competitor.pipeline import complete_v0, run_vertical_slice
from hackathon_competitor.postmortem import record_postmortem
from hackathon_competitor.storage import Database

FIXTURE = Path(__file__).parent / "fixtures/hackathon/official.html"


def test_postmortem_records_explicit_outcome_and_cross_mission_lesson(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    app = MissionOrchestrator(database, tmp_path / "missions")
    mission = run_vertical_slice(app, str(FIXTURE))
    mission = complete_v0(app, mission.id)
    artifact = record_postmortem(
        app,
        mission.id,
        outcome="Ready locally; live submission not attempted.",
        lessons=["Keep the evidence trail visible in the first user interaction."],
    )
    assert mission.state == MissionState.READY_FOR_SUBMISSION
    assert Path(artifact.path).read_text().startswith("# Mission postmortem")
    assert database.list_competition_memory(category="postmortem_lesson")[0].content.startswith(
        "Keep"
    )


def test_postmortem_rejects_implicit_or_empty_outcomes(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    app = MissionOrchestrator(database, tmp_path / "missions")
    mission = run_vertical_slice(app, str(FIXTURE))
    with pytest.raises(ValueError, match="not valid"):
        record_postmortem(app, mission.id, outcome="done", lessons=[])
