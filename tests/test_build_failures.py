"""What a failing build tells the model that has to repair it.

The first live model-built project burned its whole repair budget installing a
missing linter, then failed on the formatter it had just installed — and its
tests never ran at all, because the run stopped at the first failing command.
A repair is only as good as the failure it is shown.
"""

from hackathon_competitor.build_loop import RealBuildLoop
from hackathon_competitor.models import ProjectMode, ProjectTarget
from hackathon_competitor.storage import Database
from hackathon_competitor.workspace import GitWorkspace
from hackathon_competitor.tool_gateway import LocalGitTool


def _target(tmp_path, commands):
    return ProjectTarget(
        mission_id=__import__("uuid").uuid4(),
        mode=ProjectMode.LOCAL_ONLY,
        local_path=str(tmp_path),
        default_branch="main",
        **commands,
    )


def _loop(tmp_path):
    database = Database(tmp_path / "state.db")
    database.migrate()
    return RealBuildLoop(database, tmp_path / "artifacts"), database


def test_every_failure_reaches_the_repair_not_only_the_first(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    loop, database = _loop(tmp_path)
    target = _target(
        project,
        {
            "lint_commands": [["python3", "-c", "raise SystemExit('style is wrong')"]],
            "test_commands": [["python3", "-c", "raise SystemExit('a test fails')"]],
        },
    )
    workspace = GitWorkspace(project)
    workspace.initialize(default_branch="main")
    (project / "keep.txt").write_text("x", encoding="utf-8")
    workspace.checkpoint("seed")
    git = LocalGitTool(project, shell=workspace.shell)

    passed, failure = loop._run_commands(
        target,
        [("lint", target.lint_commands[0]), ("test", target.test_commands[0])],
        git,
    )

    assert passed is False
    assert "[lint]" in failure
    assert "[test]" in failure
    phases = [run.phase for run in database.list_build_runs(target.mission_id)]
    assert phases == ["lint", "test"]


def test_a_failed_install_stops_immediately(tmp_path):
    """Nothing downstream of a broken environment means anything."""

    project = tmp_path / "project"
    project.mkdir()
    loop, database = _loop(tmp_path)
    target = _target(
        project,
        {
            "install_commands": [["python3", "-c", "raise SystemExit('no environment')"]],
            "test_commands": [["python3", "-c", "print('unreachable')"]],
        },
    )
    workspace = GitWorkspace(project)
    workspace.initialize(default_branch="main")
    (project / "keep.txt").write_text("x", encoding="utf-8")
    workspace.checkpoint("seed")
    git = LocalGitTool(project, shell=workspace.shell)

    passed, failure = loop._run_commands(
        target,
        [("install", target.install_commands[0]), ("test", target.test_commands[0])],
        git,
    )

    assert passed is False
    assert "[install]" in failure
    assert "[test]" not in failure
    assert [run.phase for run in database.list_build_runs(target.mission_id)] == ["install"]
