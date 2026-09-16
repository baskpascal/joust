from hackathon_competitor.models import GitHubConnectionStatus
from hackathon_competitor.presentation import (
    PresentationMode,
    presentation_mode,
    public_mission_facts,
    render_answer,
    render_github_connection,
    render_project_ready,
)


def test_details_mode_requires_an_explicit_technical_request():
    assert presentation_mode("Where is my project?") is PresentationMode.NORMAL
    assert presentation_mode("Can you cancel it?") is PresentationMode.NORMAL
    assert presentation_mode("Show technical details") is PresentationMode.DETAILS
    assert presentation_mode("Which branch is it on?") is PresentationMode.DETAILS


def test_public_facts_keep_product_assets_and_drop_runtime_details():
    facts = {
        "mission_id": "b6d3f8b1-3f2f-4ff1-9bc6-bb0aa9fcb0bc",
        "state": "READY_FOR_SUBMISSION",
        "competition": "AI Worth Using",
        "competition_url": "https://aiworthusing.com/agent-index",
        "project": {
            "name": "RampBot",
            "path": "/var/lib/hermes/home/rampbot",
            "branch": "joust/b6d3f8b1-3f2f-4ff1-9bc6-bb0aa9fcb0bc",
            "repository_url": "https://github.com/alice/rampbot",
            "test_commands": [["pytest"]],
            "tests_passed": 31,
            "git_history_saved": True,
        },
    }

    public = public_mission_facts(
        facts,
        github=GitHubConnectionStatus(connected=True, login="alice"),
    )

    assert public["state"] == "ready"
    assert public["project"] == {
        "name": "RampBot",
        "location": "repository",
        "repository_url": "https://github.com/alice/rampbot",
        "tests_passed": 31,
        "git_history_saved": True,
    }
    assert "mission_id" not in public
    assert "path" not in public["project"]
    assert "branch" not in public["project"]
    assert public["github"]["login"] == "alice"


def test_normal_renderer_redacts_infrastructure_but_details_preserve_it():
    technical = (
        "The project lives at /var/lib/hermes/home/rampbot in galahad-agent-1. "
        "MissionOrchestrator uses branch joust/b6d3f8b1-3f2f-4ff1-9bc6-bb0aa9fcb0bc; "
        "orchestrator-level cancel() is available; gh auth is available."
    )

    normal = render_answer(technical)

    assert "/var/lib/hermes" not in normal
    assert "galahad-agent-1" not in normal
    assert "MissionOrchestrator" not in normal
    assert "orchestrator" not in normal.casefold()
    assert "cancel()" not in normal
    assert "gh auth" not in normal
    assert "filesystem" not in normal.casefold()
    assert "branch" not in normal.casefold()
    assert "path:" not in normal.casefold()
    assert "b6d3f8b1-3f2f-4ff1-9bc6-bb0aa9fcb0bc" not in normal
    assert render_answer(technical, mode=PresentationMode.DETAILS) == technical


def test_github_connection_uses_installation_language():
    disconnected = render_github_connection(GitHubConnectionStatus(connected=False))
    connected = render_github_connection(
        GitHubConnectionStatus(connected=True, login="alice", can_push_to_target=True)
    )
    denied = render_github_connection(
        GitHubConnectionStatus(connected=True, login="alice", can_push_to_target=False)
    )

    assert "isn't connected" in disconnected
    assert "GitHub connected: alice." == connected
    assert "can't push" in denied
    assert "your account" not in connected.casefold()


def test_ready_project_renderer_never_invents_a_repository_url():
    ready = render_project_ready(
        name="RampBot",
        tests_passed=31,
        github=GitHubConnectionStatus(connected=True, login="alice"),
    )

    assert "RampBot is ready." in ready
    assert "✓ 31 tests pass" in ready
    assert "GitHub connected: alice." in ready
    assert "It hasn't been published yet." in ready
    assert "github.com" not in ready
