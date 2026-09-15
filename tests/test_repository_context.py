"""Test 15 found the actual architectural gap: strategize()/plan_project()
had no way to know a repository already existed, let alone what was in it.
This is the missing input, tested on its own before it is wired into any
prompt: a bounded, read-only snapshot, built without executing anything
from the repository it describes.
"""

from __future__ import annotations

import subprocess

from hackathon_competitor.capabilities.repository_context import inspect_repository


def _git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _seed_python_project(root):
    (root / "pkg").mkdir()
    (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (root / "pkg" / "core.py").write_text(
        "def tokenize(text):\n"
        "    return text.split()\n"
        "\n\n"
        "def _private_helper():\n"
        "    pass\n"
        "\n\n"
        "class Report:\n"
        "    pass\n",
        encoding="utf-8",
    )
    (root / "pkg" / "todo_module.py").write_text(
        "def export():\n    # TODO: implement CSV export\n    raise NotImplementedError\n",
        encoding="utf-8",
    )
    (root / "tests").mkdir()
    (root / "tests" / "test_core.py").write_text(
        "from pkg.core import tokenize\n\ndef test_tokenize():\n    assert tokenize('a b') == ['a', 'b']\n",
        encoding="utf-8",
    )
    (root / "README.md").write_text("# pkg\n\nA small real package.\n", encoding="utf-8")
    (root / "pyproject.toml").write_text("[project]\nname='pkg'\n", encoding="utf-8")
    _git(root, "init", "-q", "-b", "trunk")
    _git(root, "add", "-A")
    _git(root, "-c", "user.email=a@b.c", "-c", "user.name=x", "commit", "-qm", "seed the package")


def test_inspect_repository_reads_language_tree_readme_and_git_state(tmp_path):
    _seed_python_project(tmp_path)

    context = inspect_repository(tmp_path)

    assert context.language == "Python"
    assert "pkg/core.py" in context.tree
    assert "tests/test_core.py" in context.test_files
    assert context.readme_excerpt.startswith("# pkg")
    assert context.current_branch == "trunk"
    assert context.commit_count == 1
    assert context.latest_commit_message == "seed the package"


def test_inspect_repository_extracts_public_api_and_excludes_private_and_tests(tmp_path):
    _seed_python_project(tmp_path)

    context = inspect_repository(tmp_path)

    joined = "\n".join(context.public_api)
    assert "def tokenize(text)" in joined
    assert "class Report" in joined
    assert "_private_helper" not in joined
    assert not any("test_core" in entry for entry in context.public_api)


def test_inspect_repository_finds_real_todos(tmp_path):
    _seed_python_project(tmp_path)

    context = inspect_repository(tmp_path)

    assert any("TODO: implement CSV export" in todo for todo in context.todos)


def test_inspect_repository_on_a_directory_with_no_git_or_readme_is_still_safe(tmp_path):
    (tmp_path / "main.go").write_text("package main\n", encoding="utf-8")

    context = inspect_repository(tmp_path)

    assert context.current_branch is None
    assert context.commit_count == 0
    assert context.readme_excerpt is None
    assert context.tree == ["main.go"]


def test_inspect_repository_never_executes_anything_from_the_repo(tmp_path):
    """The one property that matters most: a malicious or broken install/test
    script in the repository must never run just from being inspected."""

    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "conftest.py").write_text(
        "raise SystemExit('this must never execute during inspection')\n", encoding="utf-8"
    )
    (tmp_path / "setup.py").write_text(
        "raise SystemExit('this must never execute during inspection')\n", encoding="utf-8"
    )

    context = inspect_repository(tmp_path)  # must not raise / exit

    assert context.language == "Python"
