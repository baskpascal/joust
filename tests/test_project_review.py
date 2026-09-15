from pathlib import Path
from uuid import uuid4

from hackathon_competitor.models import BuildRun, ChangeSet, ProjectMode, ProjectTarget
from hackathon_competitor.project_review import review_project_change


def _target(tmp_path):
    mission_id = uuid4()
    root = tmp_path / "project"
    root.mkdir()
    target = ProjectTarget(
        mission_id=mission_id,
        mode=ProjectMode.LOCAL_ONLY,
        local_path=str(root),
    )
    return target, ChangeSet(
        mission_id=mission_id,
        project_target_id=target.id,
        base_sha="base",
        diff_hash="diff",
        files=["app.py", "test_app.py", "README.md"],
        commit_sha="commit",
        status="validated",
    )


def test_project_review_uses_changed_files_and_clean_test_evidence(tmp_path):
    target, change_set = _target(tmp_path)
    for name in change_set.files:
        (Path(target.local_path) / name).write_text("print('ok')\n", encoding="utf-8")
    runs = [
        BuildRun(
            mission_id=target.mission_id,
            project_target_id=target.id,
            command=["pytest"],
            phase="test",
            passed=True,
        ),
        BuildRun(
            mission_id=target.mission_id,
            project_target_id=target.id,
            command=["pytest"],
            phase="reproduce_test",
            passed=True,
        ),
    ]
    result = review_project_change(target, change_set, runs)
    assert result["passed"] is True
    assert result["blocking_findings"] == []


def test_project_review_blocks_possible_secret(tmp_path):
    target, change_set = _target(tmp_path)
    (Path(target.local_path) / "app.py").write_text(
        "PLOW_AGENT_TOKEN='do-not-commit'\n", encoding="utf-8"
    )
    (Path(target.local_path) / "test_app.py").write_text("def test_ok(): pass\n", encoding="utf-8")
    (Path(target.local_path) / "README.md").write_text("# App\n", encoding="utf-8")
    result = review_project_change(
        target,
        change_set,
        [
            BuildRun(
                mission_id=target.mission_id,
                project_target_id=target.id,
                command=["pytest"],
                phase="test",
                passed=True,
            )
        ],
    )
    assert result["passed"] is False
    assert any("secret" in item for item in result["blocking_findings"])


def test_a_validated_no_diff_change_set_is_never_blocked(tmp_path):
    """A dependency reinstall or a config fix can validate cleanly with no
    changed files at all. Requiring the caller to have predicted that in
    advance (the old `verification_only` requirement) blocked exactly this
    outcome once already, forcing an unneeded extra repair round."""

    mission_id = uuid4()
    root = tmp_path / "project"
    root.mkdir()
    target = ProjectTarget(mission_id=mission_id, mode=ProjectMode.LOCAL_ONLY, local_path=str(root))
    change_set = ChangeSet(
        mission_id=mission_id,
        project_target_id=target.id,
        base_sha="base",
        diff_hash="diff",
        files=[],
        commit_sha="commit",
        status="validated",
        verification_only=False,
    )
    runs = [
        BuildRun(
            mission_id=target.mission_id,
            project_target_id=target.id,
            command=["pytest"],
            phase="test",
            passed=True,
        ),
        BuildRun(
            mission_id=target.mission_id,
            project_target_id=target.id,
            command=["pytest"],
            phase="reproduce_test",
            passed=True,
        ),
    ]
    result = review_project_change(target, change_set, runs)
    assert result["passed"] is True
    assert result["blocking_findings"] == []
    assert any("no source files changed" in item for item in result["findings"])
