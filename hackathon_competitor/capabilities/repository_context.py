"""Read what already exists in a project, before any strategy is proposed.

Test 15 (an unseen competition against a real, partially-built repository)
found that `strategize`/`plan_project` had no input for "what does the
existing project already look like" — the code path that chose a strategy
simply never received the repository's contents, so it could not have
referenced them no matter how capable the model was. The implementation
step alone (which does have file access) is what saved the outcome that
time. This module is the missing input: a bounded, read-only, static
snapshot of an existing repository, built without executing anything from
it — no install command, no test command, nothing beyond reading file names
and a bounded slice of file contents, plus read-only Git metadata.
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

from ..models import RepositoryContext

MAX_TREE_ENTRIES = 200
MAX_PUBLIC_API_ENTRIES = 60
MAX_TODO_ENTRIES = 30
MAX_README_CHARS = 2000

_IGNORED_DIR_NAMES = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".next",
}
_TEST_FILE_PATTERN = re.compile(
    r"(^|/)(test_[^/]+\.py|[^/]+_test\.py|[^/]+\.test\.[jt]sx?|[^/]+\.spec\.[jt]sx?)$"
)
_TODO_PATTERN = re.compile(r"#\s*(TODO|FIXME)[:\s].*|//\s*(TODO|FIXME)[:\s].*", re.IGNORECASE)
_LANGUAGE_MARKERS = (
    ("pyproject.toml", "Python", None),
    ("setup.py", "Python", None),
    ("package.json", "JavaScript/TypeScript", None),
    ("Cargo.toml", "Rust", None),
    ("go.mod", "Go", None),
    ("build.gradle.kts", "Kotlin", "Gradle"),
    ("build.gradle", "Java/Kotlin", "Gradle"),
    ("pom.xml", "Java", "Maven"),
    ("Gemfile", "Ruby", None),
)


def detect_default_branch(path: Path) -> str | None:
    """The branch a real checkout is actually on. Read-only; writes nothing."""

    if not (path / ".git").is_dir():
        return None
    result = _run_git(path, ["symbolic-ref", "--short", "HEAD"])
    return result if result else None


def _run_git(path: Path, args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _walk_tree(root: Path) -> list[str]:
    entries: list[str] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if _IGNORED_DIR_NAMES.intersection(relative.parts):
            continue
        if path.is_file():
            entries.append(str(relative))
        if len(entries) >= MAX_TREE_ENTRIES:
            break
    return entries


def _detect_language_and_framework(root: Path, tree: list[str]) -> tuple[str | None, str | None]:
    names = {Path(entry).name for entry in tree}
    for marker, language, framework in _LANGUAGE_MARKERS:
        if marker in names:
            return language, framework
    return None, None


def _read_readme_excerpt(root: Path) -> str | None:
    for name in ("README.md", "README.rst", "README.txt", "README"):
        candidate = root / name
        if candidate.is_file():
            try:
                return candidate.read_text(encoding="utf-8", errors="replace")[:MAX_README_CHARS]
            except OSError:
                return None
    return None


def _python_public_api(root: Path, tree: list[str]) -> list[str]:
    """Top-level function and class signatures, via `ast` — never executed."""

    signatures: list[str] = []
    for relative in tree:
        if not relative.endswith(".py") or _TEST_FILE_PATTERN.search(relative):
            continue
        try:
            source = (root / relative).read_text(encoding="utf-8", errors="replace")
            tree_node = ast.parse(source, filename=relative)
        except (OSError, SyntaxError):
            continue
        for node in tree_node.body:
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                if node.name.startswith("_"):
                    continue
                params = ", ".join(arg.arg for arg in node.args.args)
                signatures.append(f"{relative}: def {node.name}({params})")
            elif isinstance(node, ast.ClassDef):
                if node.name.startswith("_"):
                    continue
                signatures.append(f"{relative}: class {node.name}")
            if len(signatures) >= MAX_PUBLIC_API_ENTRIES:
                return signatures
    return signatures


def _find_todos(root: Path, tree: list[str]) -> list[str]:
    findings: list[str] = []
    text_suffixes = {
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".go",
        ".rs",
        ".java",
        ".kt",
        ".rb",
        ".md",
    }
    for relative in tree:
        if Path(relative).suffix not in text_suffixes:
            continue
        try:
            lines = (root / relative).read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for number, line in enumerate(lines, start=1):
            if _TODO_PATTERN.search(line):
                findings.append(f"{relative}:{number}: {line.strip()}"[:200])
            if len(findings) >= MAX_TODO_ENTRIES:
                return findings
    return findings


def inspect_repository(path: str | Path) -> RepositoryContext:
    """Build a read-only snapshot of an existing local repository.

    Bounded on every axis (tree, public API, TODOs) so this cannot itself
    become the kind of unbounded-prompt problem `_bounded_failure` exists to
    prevent elsewhere: a huge repository yields a capped, representative
    sample, not everything.
    """

    root = Path(path).resolve()
    tree = _walk_tree(root)
    language, framework = _detect_language_and_framework(root, tree)
    test_files = [entry for entry in tree if _TEST_FILE_PATTERN.search(entry)]
    commit_count_text = _run_git(root, ["rev-list", "--count", "HEAD"])
    return RepositoryContext(
        local_path=str(root),
        language=language,
        framework=framework,
        tree=tree,
        readme_excerpt=_read_readme_excerpt(root),
        test_files=test_files,
        public_api=_python_public_api(root, tree),
        todos=_find_todos(root, tree),
        current_branch=detect_default_branch(root),
        commit_count=int(commit_count_text)
        if commit_count_text and commit_count_text.isdigit()
        else 0,
        latest_commit_message=_run_git(root, ["log", "-1", "--format=%s"]),
    )


__all__ = ["detect_default_branch", "inspect_repository"]
