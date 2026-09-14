from __future__ import annotations

import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Protocol


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
    def current_revision(self) -> str: ...
    def create_branch(self, name: str, base: str) -> str: ...
    def diff(self) -> str: ...
    def changed_files(self) -> list[str]: ...


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

    def __init__(self, root: str | Path, *, environment: Mapping[str, str] | None = None):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.environment = dict(environment) if environment is not None else None

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
                env=self.environment,
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

    def current_revision(self) -> str:
        return self.shell.run(["git", "rev-parse", "HEAD"], timeout_seconds=15).strip()

    def create_branch(self, name: str, base: str) -> str:
        if not name.strip() or name.startswith("-"):
            raise ValueError("branch name must be non-empty and cannot start with '-'")
        self.shell.run(["git", "switch", "-c", name, base], timeout_seconds=30)
        return self.current_revision()

    def current_branch(self) -> str:
        return self.shell.run(["git", "branch", "--show-current"], timeout_seconds=15).strip()

    def branch_exists(self, name: str) -> bool:
        if not name or name.startswith("-"):
            raise ValueError("invalid branch name")
        output = self.shell.run(["git", "branch", "--list", name], timeout_seconds=15)
        return bool(output.strip())

    def switch_branch(self, name: str) -> str:
        if not name or name.startswith("-"):
            raise ValueError("invalid branch name")
        self.shell.run(["git", "switch", name], timeout_seconds=30)
        return self.current_revision()

    def diff(self) -> str:
        return self.shell.run(["git", "diff", "--no-ext-diff"], timeout_seconds=30)

    def changed_files(self) -> list[str]:
        output = self.shell.run(["git", "status", "--short", "--porcelain=v1"], timeout_seconds=15)
        # LocalShellTool combines stdout/stderr; ignore trace/warning lines and
        # retain only porcelain records (two status bytes followed by a space).
        valid = set(" MADRCU?!")
        return [
            line[3:]
            for line in output.splitlines()
            if len(line) >= 4 and line[2] == " " and line[0] in valid and line[1] in valid
        ]

    def commit_diff(self, commit_sha: str) -> str:
        return self.shell.run(
            ["git", "show", "--format=", "--no-ext-diff", commit_sha], timeout_seconds=30
        )

    def commit_changed_files(self, commit_sha: str) -> list[str]:
        output = self.shell.run(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", commit_sha],
            timeout_seconds=15,
        )
        return [line.strip() for line in output.splitlines() if line.strip()]


class CodingAgentCommandTool:
    """Handoff adapter for a configured local coding-agent command."""

    policy = OperationPolicy(
        900,
        False,
        "local_write",
        "one specification file and one isolated Git workspace",
        "review Git diff and restore or amend the checkpoint",
    )

    def __init__(
        self,
        root: str | Path,
        command_prefix: list[str],
        *,
        environment: Mapping[str, str] | None = None,
    ):
        if not command_prefix:
            raise ValueError("coding agent command prefix cannot be empty")
        self.root = Path(root).resolve()
        self.files = WorkspaceFileTool(self.root)
        self.shell = LocalShellTool(self.root, environment=environment)
        self.command_prefix = list(command_prefix)

    def implement(self, specification: str) -> str:
        relative = ".joust/coding-agent-handoff.md"
        self.files.write_text(relative, specification)
        return self.shell.run(
            [*self.command_prefix, relative],
            timeout_seconds=self.policy.timeout_seconds,
        )


class PlowLatchAdapter:
    """Structured boundary for Plow/Latch-backed browser, shell, and file tools."""

    policies: ClassVar[dict[str, OperationPolicy]] = {
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
