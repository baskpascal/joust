from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Protocol


class BrowserTool(Protocol):
    def open(self, url: str) -> str: ...


class ShellTool(Protocol):
    def run(self, argv: list[str], *, timeout_seconds: float) -> str: ...


class FileTool(Protocol):
    def read_text(self, path: str) -> str: ...
    def write_text(self, path: str, content: str) -> None: ...


class GitTool(Protocol):
    def status(self) -> str: ...


class CodingAgentTool(Protocol):
    def implement(self, specification: str) -> str: ...


class DeployTool(Protocol):
    def deploy(self, target: str) -> str: ...


class MessagingTool(Protocol):
    def send(self, recipient: str, message: str) -> str: ...


class WorkspaceFileTool:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def _resolve(self, path: str) -> Path:
        candidate = (self.root / path).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise PermissionError(f"path escapes mission workspace: {path}")
        return candidate

    def read_text(self, path: str) -> str:
        return self._resolve(path).read_text(encoding="utf-8")

    def write_text(self, path: str, content: str) -> None:
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


class LocalShellTool:
    """Runs an argv vector inside one mission workspace without shell expansion."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def run(self, argv: list[str], *, timeout_seconds: float) -> str:
        if not argv or any(not isinstance(argument, str) for argument in argv):
            raise ValueError("argv must contain at least one string argument")
        try:
            completed = subprocess.run(
                argv,
                cwd=self.root,
                shell=False,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(f"command exceeded timeout of {timeout_seconds} seconds") from exc
        output = completed.stdout + completed.stderr
        if completed.returncode:
            raise RuntimeError(
                f"command exited with status {completed.returncode}: {output.strip()}"
            )
        return output


class LocalGitTool:
    def __init__(self, root: str | Path, shell: LocalShellTool | None = None):
        self.shell = shell or LocalShellTool(root)

    def status(self) -> str:
        return self.shell.run(
            ["git", "status", "--short", "--branch"],
            timeout_seconds=15,
        )
