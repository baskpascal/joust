"""A real Test 15 commit carried a `.egg-info/` directory into an existing
project's history because that project's own `.gitignore` had no rule for
it (nothing had generated one yet). `git add --all` already honours
`.gitignore` correctly; the gap this closes is a project whose `.gitignore`
never had reason to think about build output yet.
"""

from __future__ import annotations

import subprocess

from hackathon_competitor.workspace import GitWorkspace


def _tracked_files(root):
    return subprocess.run(
        ["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True
    ).stdout.splitlines()


def test_generated_artifacts_are_gitignored_before_the_first_commit(tmp_path):
    workspace = GitWorkspace(tmp_path)
    workspace.initialize()
    (tmp_path / "app.py").write_text("print(1)\n", encoding="utf-8")
    egg_info = tmp_path / "mypkg.egg-info"
    egg_info.mkdir()
    (egg_info / "PKG-INFO").write_text("x", encoding="utf-8")
    pycache = tmp_path / "__pycache__"
    pycache.mkdir()
    (pycache / "app.cpython-312.pyc").write_bytes(b"junk")

    workspace.checkpoint("first commit")

    tracked = _tracked_files(tmp_path)
    assert "app.py" in tracked
    assert not any("egg-info" in path for path in tracked)
    assert not any("__pycache__" in path for path in tracked)
    gitignore = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert "*.egg-info" in gitignore
    assert "__pycache__" in gitignore


def test_an_existing_gitignore_rule_is_kept_and_not_duplicated(tmp_path):
    workspace = GitWorkspace(tmp_path)
    workspace.initialize()
    (tmp_path / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("print(1)\n", encoding="utf-8")
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "out.whl").write_bytes(b"junk")

    workspace.checkpoint("first commit")

    gitignore = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert gitignore.count("__pycache__") == 1
    assert "dist" in gitignore
    assert "dist" not in _tracked_files(tmp_path)


def test_a_project_with_no_generated_artifacts_gets_no_gitignore_at_all(tmp_path):
    workspace = GitWorkspace(tmp_path)
    workspace.initialize()
    (tmp_path / "app.py").write_text("print(1)\n", encoding="utf-8")

    workspace.checkpoint("first commit")

    assert not (tmp_path / ".gitignore").is_file()
