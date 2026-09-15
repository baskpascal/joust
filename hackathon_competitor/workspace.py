from __future__ import annotations

import subprocess
from collections.abc import Mapping
from pathlib import Path

from .tool_gateway import LocalShellTool

# Directories and files that are near-universally build/tool output, never
# hand-written source: committing them is noise at best (a real commit
# during Test 15 carried a `.egg-info/` directory into history because the
# repo's own `.gitignore` had no rule for it) and a possible credential leak
# at worst (`.env`-adjacent caches). `git add --all` already honours
# `.gitignore` correctly; the gap is a repository whose `.gitignore` simply
# never had to think about these, because nothing had generated them yet.
_GENERATED_ARTIFACT_PATTERNS = (
    "*.egg-info",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".next",
    ".DS_Store",
    ".coverage",
)


class GitWorkspace:
    """Small Git boundary for a mission-owned project directory."""

    def __init__(self, root: str | Path, *, environment: Mapping[str, str] | None = None):
        self.root = Path(root).resolve()
        self.shell = LocalShellTool(self.root, environment=environment)

    def initialize(self, *, default_branch: str = "main") -> None:
        if not (self.root / ".git").is_dir():
            self.shell.run(["git", "init", "-b", default_branch], timeout_seconds=30)

    def _unignored_generated_artifacts(self) -> list[str]:
        """Which known-junk patterns exist on disk but aren't already covered
        by the repository's own ignore rules. Uses `git check-ignore` itself
        rather than reimplementing gitignore matching, so an existing broader
        rule (`build/`, a nested `.gitignore`, a negation) is respected."""

        found: list[str] = []
        for pattern in _GENERATED_ARTIFACT_PATTERNS:
            matches = [
                path
                for path in self.root.glob(f"**/{pattern}")
                if ".git" not in path.relative_to(self.root).parts
            ]
            if not matches:
                continue
            sample = str(matches[0].relative_to(self.root))
            result = subprocess.run(
                ["git", "check-ignore", "-q", sample],
                cwd=self.root,
                env=self.shell.environment,
                capture_output=True,
                timeout=10,
                check=False,
            )
            if result.returncode != 0:  # 0 = already ignored; 1 = not ignored
                found.append(pattern)
        return found

    def _ignore_generated_artifacts(self) -> None:
        """Add any present-but-unignored junk patterns to .gitignore, so the
        commit this checkpoint is about to make never picks them up. Creates
        .gitignore if the project doesn't have one yet."""

        missing = self._unignored_generated_artifacts()
        if not missing:
            return
        gitignore = self.root / ".gitignore"
        existing = gitignore.read_text(encoding="utf-8") if gitignore.is_file() else ""
        separator = "" if not existing or existing.endswith("\n") else "\n"
        gitignore.write_text(existing + separator + "\n".join(missing) + "\n", encoding="utf-8")

    def checkpoint(self, message: str) -> str:
        if not message.strip():
            raise ValueError("commit message cannot be empty")
        self.initialize()
        self._ignore_generated_artifacts()
        self.shell.run(["git", "add", "--all"], timeout_seconds=30)
        staged = self.shell.run(["git", "diff", "--cached", "--name-only"], timeout_seconds=15)
        if staged.strip():
            self.shell.run(
                [
                    "git",
                    "-c",
                    "core.editor=true",
                    "-c",
                    "user.name=Joust Mission Agent",
                    "-c",
                    "user.email=joust@localhost",
                    "commit",
                    "-m",
                    message,
                ],
                timeout_seconds=30,
            )
        return self.shell.run(["git", "rev-parse", "HEAD"], timeout_seconds=15).strip()
