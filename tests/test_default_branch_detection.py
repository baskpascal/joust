"""A real incident: attach-project assumed `--default-branch main` regardless
of what a checkout actually used, and broke with an opaque
`fatal: invalid reference: main` at the first build against a repository
still on `master` (an older `git init` default). Both the detection at
attach time and a self-correcting fallback in the build loop are covered.
"""

from __future__ import annotations

import subprocess

from hackathon_competitor.build_loop import RealBuildLoop
from hackathon_competitor.cli import detect_default_branch
from hackathon_competitor.models import ProjectMode, ProjectTarget
from hackathon_competitor.storage import Database


def _git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def test_detect_default_branch_reads_the_real_checked_out_branch(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "master")
    _git(repo, "-c", "user.email=a@b.c", "-c", "user.name=x", "commit", "--allow-empty", "-qm", "x")
    assert detect_default_branch(repo) == "master"


def test_detect_default_branch_is_none_without_a_git_directory(tmp_path):
    repo = tmp_path / "not-a-repo"
    repo.mkdir()
    assert detect_default_branch(repo) is None


def test_the_build_loop_self_corrects_a_stale_recorded_default_branch(tmp_path):
    """Even if a ProjectTarget was recorded with the wrong default_branch by
    some other path, the build loop must not crash trying to branch off a
    reference that was never real — it corrects from the actual checkout."""

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "master")
    (repo / "README.md").write_text("# existing\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.email=a@b.c", "-c", "user.name=x", "commit", "-qm", "seed")

    database = Database(tmp_path / "state.db")
    database.migrate()
    target = ProjectTarget(
        mission_id=__import__("uuid").uuid4(),
        mode=ProjectMode.LOCAL_ONLY,
        local_path=str(repo),
        default_branch="main",  # wrong on purpose: the repo is really on master
        test_commands=[["python3", "-c", "print(1)"]],
    )
    database.save_project_target(target)

    class _NoopImplementer:
        def implement(self, project_root, specification, failure=None):
            return "noop"

    loop = RealBuildLoop(database, tmp_path / "artifacts")
    loop.run(target, "spec", _NoopImplementer(), allow_no_changes=True)

    corrected = database.get_project_target(target.id)
    assert corrected.default_branch == "master"
    assert any(
        event["event_type"] == "PROJECT_DEFAULT_BRANCH_CORRECTED"
        for event in database.events(target.mission_id)
    )
