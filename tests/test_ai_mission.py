"""The mission as a thing you can talk to and redirect.

A mission that forgets what it decided, or that answers a question from the
model's general knowledge rather than from its own record, is not an agent
operating a competition entry. These cases hold the two properties that make
the difference: answers come only from stored state, and a change of direction
keeps the history it changes.
"""

import json

import pytest

from hackathon_competitor.ai import UnavailableReasoner
from hackathon_competitor.ai_mission import MissionBlocked, ask, joust_it, redirect
from hackathon_competitor.models import MissionState
from hackathon_competitor.orchestrator import MissionOrchestrator
from hackathon_competitor.storage import Database
from test_ai_strategy import ScriptedReasoner, _candidate


def _generation() -> dict:
    return {
        "winning_mechanism_analysis": "rank comes from reported usage",
        "candidates": [
            _candidate(
                product_thesis="A CI triage agent that classifies a red build for a platform team",
                target_user="a release engineer",
                winning_mechanism="usage volume",
            ),
            _candidate(
                product_thesis="A records desk agent that drafts public-records requests",
                target_user="a reporter",
                winning_mechanism="install breadth",
            ),
            _candidate(
                product_thesis="A packaging agent that makes a repo index-ready in one command",
                target_user="a solo builder",
                winning_mechanism="rides the mandatory rules",
            ),
        ],
    }


def _plan() -> dict:
    return {
        "repository_name": "red-build-triage",
        "language": "Python",
        "framework": "none",
        "install_commands": [["python3", "-m", "venv", ".venv"]],
        "test_commands": [[".venv/bin/python", "-m", "pytest", "-q"]],
        "lint_commands": [],
        "first_slice_specification": "s" * 200,
    }


def _rules_page(tmp_path):
    page = tmp_path / "rules.html"
    page.write_text(
        """<html><body data-hackathon-name="Test Cup">
        <p>Entrants must publish a public repository to be eligible.</p>
        <p>Submissions must include a runnable demo and a README file.</p>
        <p>Entrants must not fabricate usage numbers or installs.</p>
        </body></html>""",
        encoding="utf-8",
    )
    return str(page)


@pytest.fixture
def app(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    return MissionOrchestrator(database, tmp_path / "missions")


def test_a_competition_url_becomes_a_chosen_strategy_and_a_real_project(app, tmp_path):
    reasoner = ScriptedReasoner(
        _generation(),
        {"selected_index": 0, "rationale": "r" * 60, "rejected": []},
        _plan(),
    )
    mission, selected, decision, target = joust_it(
        app,
        _rules_page(tmp_path),
        reasoner,
        workspace_path=str(tmp_path / "work"),
        projects_root=tmp_path / "projects",
    )

    assert mission.state is MissionState.BUILDING
    assert len(decision.options) == 3
    assert decision.selected_option == str(selected.id)
    assert target.local_path.endswith("red-build-triage")
    assert (tmp_path / "projects" / "red-build-triage").is_dir()
    slice_path = app.artifact_root / str(mission.id) / "artifacts" / "FIRST_SLICE.md"
    assert slice_path.is_file()

    events = {event["event_type"] for event in app.database.events(mission.id)}
    assert {"AI_STRATEGY_SELECTED", "AI_PROJECT_PLANNED"} <= events


def test_without_a_model_the_mission_blocks_and_creates_no_project(app, tmp_path):
    """The ablation, through the path a user actually runs."""

    with pytest.raises(MissionBlocked) as caught:
        joust_it(
            app,
            _rules_page(tmp_path),
            UnavailableReasoner(),
            workspace_path=str(tmp_path / "work"),
            projects_root=tmp_path / "projects",
        )

    assert caught.value.code == "AI_STRATEGY_UNAVAILABLE"
    mission = app.database.get_mission(caught.value.mission_id)
    assert mission.state is MissionState.BLOCKED
    assert not (tmp_path / "projects").exists()
    assert app.database.list_strategy_candidates(mission.id) == []


def test_an_unreadable_competition_blocks_before_any_model_is_asked(app, tmp_path):
    shell = tmp_path / "shell.html"
    shell.write_text("<html><body><div id='app'></div></body></html>", encoding="utf-8")
    reasoner = ScriptedReasoner(_generation())

    with pytest.raises(MissionBlocked) as caught:
        joust_it(app, str(shell), reasoner, workspace_path=str(tmp_path / "work"))

    assert caught.value.code == "SOURCE_UNREADABLE"
    assert reasoner.prompts == []


def test_a_question_is_answered_from_stored_state_only(app, tmp_path):
    reasoner = ScriptedReasoner(
        _generation(),
        {"selected_index": 0, "rationale": "r" * 60, "rejected": []},
        _plan(),
        "The mission is building red-build-triage.",
    )
    mission, _, _, _ = joust_it(
        app,
        _rules_page(tmp_path),
        reasoner,
        workspace_path=str(tmp_path / "work"),
        projects_root=tmp_path / "projects",
    )

    answer = ask(app, mission.id, "What have you built?", reasoner)

    assert answer == "The mission is building red-build-triage."
    question_prompt = reasoner.prompts[-1]
    facts = json.loads(question_prompt.split("facts=", 1)[1])
    assert facts["competition"] == "Test Cup"
    assert facts["project"]["path"].endswith("red-build-triage")
    assert len(facts["strategies_considered"]) == 3
    assert "using only the facts" in question_prompt


def test_a_redirect_changes_course_without_losing_the_record(app, tmp_path):
    reasoner = ScriptedReasoner(
        _generation(),
        {"selected_index": 0, "rationale": "r" * 60, "rejected": []},
        _plan(),
        {
            "selected_index": 2,
            "rationale": "installation is the failing step and this one needs no account " * 2,
            "what_still_stands": "the rules evidence and the project scaffold",
        },
    )
    mission, first_choice, first_decision, _ = joust_it(
        app,
        _rules_page(tmp_path),
        reasoner,
        workspace_path=str(tmp_path / "work"),
        projects_root=tmp_path / "projects",
    )

    selected, ai_decision = redirect(
        app,
        mission.id,
        "Users are failing installation; pursue the one that installs without an account.",
        reasoner,
    )

    assert selected.id != first_choice.id
    assert ai_decision.decision_type == "strategy_reassessment"
    assert ai_decision.rationale.startswith("Users are failing installation")

    # Nothing from before the redirect is discarded.
    assert len(app.database.list_strategy_candidates(mission.id)) == 3
    assert first_decision.id in {item.id for item in app.database.list_decisions(mission.id)}
    assert app.database.list_evidence(mission.id)
    reassessed = app.database.get_mission(mission.id)
    assert reassessed.active_strategy_id != first_decision.id
    assert reassessed.selected_strategy_id == first_decision.id
    events = [
        item
        for item in app.database.events(mission.id)
        if item["event_type"] == "STRATEGY_REASSESSED"
    ]
    assert events and events[-1]["payload"]["what_still_stands"]


def test_a_redirect_that_picks_nothing_valid_is_refused(app, tmp_path):
    reasoner = ScriptedReasoner(
        _generation(),
        {"selected_index": 0, "rationale": "r" * 60, "rejected": []},
        _plan(),
        {"selected_index": 7, "rationale": "x" * 60},
    )
    mission, _, _, _ = joust_it(
        app,
        _rules_page(tmp_path),
        reasoner,
        workspace_path=str(tmp_path / "work"),
        projects_root=tmp_path / "projects",
    )
    with pytest.raises(MissionBlocked, match="REDIRECT_SELECTION_INVALID"):
        redirect(app, mission.id, "change course", reasoner)
