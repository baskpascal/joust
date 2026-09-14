from datetime import UTC, datetime, timedelta
from pathlib import Path

from hackathon_competitor.compete_loop import CompeteLoop
from hackathon_competitor.models import (
    BuildRun,
    ChangeSet,
    CompetitionRule,
    HackathonSpec,
    Mission,
    ProjectMode,
    ProjectTarget,
)
from hackathon_competitor.observation import CompetitionObserver
from hackathon_competitor.storage import MIGRATIONS, Database
from hackathon_competitor.workspace import GitWorkspace


class FakeGitHub:
    def __init__(self):
        self.calls = []

    def checks(self, repository, ref):
        self.calls.append((repository, ref))
        return [{"name": "tests", "state": "SUCCESS", "link": "https://example.test"}]


class FakeDeployment:
    def health(self, target):
        return {"target": target, "healthy": True}


class MissingGitHub:
    def checks(self, repository, ref):
        raise FileNotFoundError("gh is unavailable")


def test_observation_plane_captures_real_local_project_state(tmp_path):
    database = Database(tmp_path / "state.db")
    assert database.migrate() == len(MIGRATIONS)
    project = tmp_path / "entry"
    project.mkdir()
    workspace = GitWorkspace(project)
    workspace.initialize()
    (project / "README.md").write_text("entry", encoding="utf-8")
    commit_sha = workspace.checkpoint("Initialize entry")
    mission = Mission(title="Joust", objective="win", workspace_path=str(project))
    database.save_mission(mission)
    spec = HackathonSpec(
        mission_id=mission.id,
        name="Competition",
        final_snapshot_at=datetime.now(UTC) + timedelta(days=1),
    )
    database.save_spec(spec)
    rule = CompetitionRule(
        mission_id=mission.id,
        category="scoring",
        statement="Leaderboard rank decides",
        normalized_constraint="leaderboard_rank_decides=true",
        authority="organizer",
        confidence=1.0,
    )
    database.save_competition_rule(rule)
    target = ProjectTarget(
        mission_id=mission.id,
        mode=ProjectMode.EXISTING_REPO,
        local_path=str(project),
        repository_owner="owner",
        repository_name="entry",
        final_commit_sha=commit_sha,
        deploy_target="https://entry.example",
        test_commands=[["python", "-c", "print('ok')"]],
    )
    database.save_project_target(target)
    database.attach_project_target(mission.id, target.id)
    database.save_change_set(
        ChangeSet(
            mission_id=mission.id,
            project_target_id=target.id,
            base_sha=commit_sha,
            diff_hash="abc",
            commit_sha=commit_sha,
            status="validated",
        )
    )
    database.save_build_run(
        BuildRun(
            mission_id=mission.id,
            project_target_id=target.id,
            commit_sha=commit_sha,
            command=["python", "-c", "print('ok')"],
            phase="test",
            exit_code=0,
            passed=True,
        )
    )
    github = FakeGitHub()
    cycle = CompeteLoop(database).create_cycle(mission.id)

    observation = CompetitionObserver(database, github=github, deployment=FakeDeployment()).capture(
        cycle.id, score_signals={"leaderboard_rank": 4.0}
    )

    assert observation.deadline_state == "upcoming"
    assert observation.repository_revision == commit_sha
    assert observation.repository_dirty is False
    assert observation.latest_change_status == "validated"
    assert observation.build_summary == {"total": 1, "passed": 1, "failed": 0}
    assert observation.github_checks[0]["state"] == "SUCCESS"
    assert observation.deployment_health["healthy"] is True
    assert github.calls == [("owner/entry", commit_sha)]
    assert observation.evidence_ids
    assert database.get_competition_cycle(cycle.id).stage.value == "ASSESS"
    exported = database.export_mission(mission.id)
    assert exported["competition_observations"][0]["repository_revision"] == commit_sha


def test_observation_plane_records_missing_target_and_expired_deadline(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    mission = Mission(
        title="Expired",
        objective="win",
        workspace_path=str(Path(tmp_path) / "missing"),
        deadline_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    database.save_mission(mission)
    cycle = CompeteLoop(database).create_cycle(mission.id)

    observation = CompetitionObserver(database).capture(cycle.id)

    assert observation.deadline_state == "expired"
    assert "competition deadline has elapsed" in observation.findings
    assert "mission has no project target" in observation.uncertainties


def test_observation_plane_degrades_missing_optional_github_cli(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    project = tmp_path / "entry"
    project.mkdir()
    workspace = GitWorkspace(project)
    workspace.initialize()
    (project / "README.md").write_text("entry", encoding="utf-8")
    commit_sha = workspace.checkpoint("Initialize")
    mission = Mission(title="Observe", objective="compete", workspace_path=str(project))
    database.save_mission(mission)
    target = ProjectTarget(
        mission_id=mission.id,
        mode=ProjectMode.EXISTING_REPO,
        local_path=str(project),
        repository_url="owner/entry",
        final_commit_sha=commit_sha,
        test_commands=[["python", "-c", "print('ok')"]],
    )
    database.save_project_target(target)
    database.attach_project_target(mission.id, target.id)
    cycle = CompeteLoop(database).create_cycle(mission.id)

    observation = CompetitionObserver(database, github=MissingGitHub()).capture(cycle.id)

    assert any("GitHub checks observation failed" in item for item in observation.uncertainties)
    assert database.get_competition_cycle(cycle.id).stage.value == "ASSESS"
