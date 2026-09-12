from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class OperationPolicy:
    timeout_seconds: float
    retryable: bool
    side_effect: str
    idempotency_strategy: str
    recovery_notes: str

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("tool timeout must be positive")
        if self.side_effect not in {"read", "local_write", "external_write"}:
            raise ValueError(f"unsupported side-effect class: {self.side_effect}")


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


class PlowBackend(Protocol):
    def invoke(self, tool: str, payload: dict[str, Any], *, timeout_seconds: float) -> Any: ...


class WorkspaceFileTool:
    read_policy = OperationPolicy(10, True, "read", "content-addressed read", "retry read")
    write_policy = OperationPolicy(
        10,
        True,
        "local_write",
        "overwrite one mission-confined path",
        "restore from Git checkpoint",
    )

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

    policy = OperationPolicy(
        30,
        False,
        "local_write",
        "caller supplies an argv operation with explicit retry semantics",
        "inspect output and restore the mission Git checkpoint",
    )

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
    status_policy = OperationPolicy(15, True, "read", "read-only Git status", "retry status")

    def __init__(self, root: str | Path, shell: LocalShellTool | None = None):
        self.shell = shell or LocalShellTool(root)

    def status(self) -> str:
        return self.shell.run(
            ["git", "status", "--short", "--branch"],
            timeout_seconds=15,
        )


class CodingAgentCommandTool:
    """Handoff adapter for a configured local coding-agent command."""

    policy = OperationPolicy(
        900,
        False,
        "local_write",
        "one specification file and one isolated Git workspace",
        "review Git diff and restore or amend the checkpoint",
    )

    def __init__(self, root: str | Path, command_prefix: list[str]):
        if not command_prefix:
            raise ValueError("coding agent command prefix cannot be empty")
        self.root = Path(root).resolve()
        self.files = WorkspaceFileTool(self.root)
        self.shell = LocalShellTool(self.root)
        self.command_prefix = list(command_prefix)

    def implement(self, specification: str) -> str:
        relative = ".galahad/coding-agent-handoff.md"
        self.files.write_text(relative, specification)
        return self.shell.run(
            [*self.command_prefix, relative],
            timeout_seconds=self.policy.timeout_seconds,
        )


class PlowLatchAdapter:
    """Structured boundary for Plow/Latch-backed browser, shell, and file tools."""

    policies = {
        "browser.open": OperationPolicy(
            30, True, "read", "URL-addressed navigation", "retry or record unavailable source"
        ),
        "shell.run": OperationPolicy(
            120,
            False,
            "local_write",
            "backend operation id plus argv",
            "inspect backend state before retrying",
        ),
        "file.read": OperationPolicy(20, True, "read", "path-addressed read", "retry read"),
        "file.write": OperationPolicy(
            20,
            True,
            "local_write",
            "overwrite one approved path",
            "restore from mission Git checkpoint",
        ),
    }

    def __init__(self, backend: PlowBackend):
        self.backend = backend

    def _invoke(self, tool: str, payload: dict[str, Any]) -> str:
        policy = self.policies[tool]
        result = self.backend.invoke(tool, payload, timeout_seconds=policy.timeout_seconds)
        if isinstance(result, str):
            return result
        if isinstance(result, dict) and isinstance(result.get("content"), str):
            return result["content"]
        raise TypeError(f"Plow backend returned invalid result for {tool}")

    def open(self, url: str) -> str:
        return self._invoke("browser.open", {"url": url})

    def run(self, argv: list[str], *, timeout_seconds: float) -> str:
        if not argv:
            raise ValueError("argv cannot be empty")
        policy = self.policies["shell.run"]
        bounded_timeout = min(timeout_seconds, policy.timeout_seconds)
        result = self.backend.invoke("shell.run", {"argv": argv}, timeout_seconds=bounded_timeout)
        if isinstance(result, str):
            return result
        if isinstance(result, dict) and isinstance(result.get("content"), str):
            return result["content"]
        raise TypeError("Plow backend returned invalid shell result")

    def read_text(self, path: str) -> str:
        return self._invoke("file.read", {"path": path})

    def write_text(self, path: str, content: str) -> None:
        self._invoke("file.write", {"path": path, "content": content})
