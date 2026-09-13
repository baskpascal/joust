from __future__ import annotations

from pathlib import Path

from .tool_gateway import LocalShellTool


class GitWorkspace:
    """Small Git boundary for a mission-owned project directory."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.shell = LocalShellTool(self.root)

    def initialize(self, *, default_branch: str = "main") -> None:
        if not (self.root / ".git").is_dir():
            self.shell.run(["git", "init", "-b", default_branch], timeout_seconds=30)

    def checkpoint(self, message: str) -> str:
        if not message.strip():
            raise ValueError("commit message cannot be empty")
        self.initialize()
        self.shell.run(["git", "add", "--all"], timeout_seconds=30)
        staged = self.shell.run(["git", "diff", "--cached", "--name-only"], timeout_seconds=15)
        if staged.strip():
            self.shell.run(
                [
                    "git",
                    "-c",
                    "user.name=Galahad Mission Agent",
                    "-c",
                    "user.email=galahad@localhost",
                    "commit",
                    "-m",
                    message,
                ],
                timeout_seconds=30,
            )
        return self.shell.run(["git", "rev-parse", "HEAD"], timeout_seconds=15).strip()
