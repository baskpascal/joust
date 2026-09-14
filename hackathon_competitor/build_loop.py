from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

from .models import (
    BuildRun,
    ChangeSet,
    ModelProvenance,
    ProjectTarget,
    RepositorySnapshot,
)
from .project_review import review_project_change
from .storage import Database
from .tool_gateway import CodingAgentCommandTool, LocalGitTool, LocalShellTool
from .workspace import GitWorkspace


class BuildLoopError(RuntimeError):
    pass


_SAFE_ENVIRONMENT_KEYS = frozenset(
    {
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "HOME",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "COMSPEC",
        "LANG",
        "LC_ALL",
        # Keep project test discovery deterministic across host installations;
        # this is a control flag, never a credential.
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
    }
)
_SENSITIVE_ENV_MARKERS = (
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "API_KEY",
    "CREDENTIAL",
    "PRIVATE_KEY",
)
_SENSITIVE_COMMAND_MARKERS = (
    "PLOW_AGENT_TOKEN",
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "API_KEY",
    "PASSWORD",
    "SECRET",
    "CREDENTIAL",
    "PRIVATE_KEY",
    "ghp_",
    "github_pat_",
    "sk-",
)


def project_environment(allowlist: Sequence[str] = ()) -> dict[str, str]:
    """Return a non-secret subprocess environment for project commands.

    Build commands must not inherit the host's Plow/GitHub credentials. An
    operator may explicitly approve additional *non-sensitive* names on the
    project target; names that look like credentials are rejected outright.
    """

    names = list(allowlist)
    for name in names:
        if not isinstance(name, str) or not name or "=" in name:
            raise ValueError("environment allowlist entries must be non-empty variable names")
        upper = name.upper()
        if any(marker in upper for marker in _SENSITIVE_ENV_MARKERS):
            raise ValueError(f"refusing sensitive environment variable: {name}")
    selected = set(_SAFE_ENVIRONMENT_KEYS) | set(names)
    return {name: value for name, value in os.environ.items() if name in selected}


def validate_project_commands(commands: Sequence[Sequence[str]]) -> None:
    """Reject command vectors that would persist an obvious credential."""

    for argv in commands:
        if not argv or any(not isinstance(argument, str) or not argument for argument in argv):
            raise ValueError("project commands must be non-empty argv vectors")
        for argument in argv:
            upper = argument.upper()
            if any(marker.upper() in upper for marker in _SENSITIVE_COMMAND_MARKERS):
                raise ValueError("project command contains a credential-shaped argument")


def _provenance(implementer: object) -> ModelProvenance | None:
    """Name the model behind a diff, when the implementer is a model.

    A ChangeSet whose provenance is absent is a change no model claimed, and
    the difference has to be visible in stored state rather than inferred from
    a class name.
    """

    invocation_id = getattr(implementer, "invocation_id", None)
    provider = getattr(implementer, "provider", None)
    if provider is None:
        return None
    return ModelProvenance(
        provider=str(provider),
        model=str(getattr(implementer, "model", "unknown")),
        invocation_id=invocation_id if isinstance(invocation_id, UUID) else uuid4(),
    )


class ProjectBootstrap(Protocol):
    def clone(self, repository: str, destination: str) -> str: ...


class Implementer(Protocol):
    def implement(
        self, project_root: Path, specification: str, failure: str | None = None
    ) -> str: ...


class RepairableImplementer(Implementer, Protocol):
    def repair(self, project_root: Path, specification: str, failure: str) -> str: ...


class CommandImplementer:
    """Adapt a file-based coding-agent command to the build-loop port."""

    def __init__(
        self,
        command_prefix: list[str],
        *,
        environment: Mapping[str, str] | None = None,
    ):
        if not command_prefix:
            raise ValueError("implementation command cannot be empty")
        self.command_prefix = list(command_prefix)
        self.environment = dict(environment) if environment is not None else None

    def set_environment(self, environment: Mapping[str, str]) -> None:
        self.environment = dict(environment)

    def implement(self, project_root: Path, specification: str, failure: str | None = None) -> str:
        return CodingAgentCommandTool(
            project_root, self.command_prefix, environment=self.environment
        ).implement(specification)

    def repair(self, project_root: Path, specification: str, failure: str) -> str:
        repair_specification = (
            f"{specification}\n\nValidation failed with:\n{failure}\n\n"
            "Repair the implementation in the current workspace, preserve the intended behavior, "
            "and run the project's declared checks before returning."
        )
        return CodingAgentCommandTool(
            project_root, self.command_prefix, environment=self.environment
        ).implement(repair_specification)


class HermesImplementer:
    """Use Hermes one-shot mode as the trusted model-backed coding process.

    The Hermes process receives its runtime inference environment. Project
    install/lint/build/test commands still run through ``project_environment``
    and therefore never inherit those credentials.
    """

    def __init__(
        self,
        *,
        executable: str = "/opt/hermes/bin/hermes",
        model: str | None = None,
        reasoning: str | None = None,
        environment: Mapping[str, str] | None = None,
    ):
        self.executable = executable
        self.model = model
        self.reasoning = reasoning
        self.environment = dict(environment) if environment is not None else os.environ.copy()

    def _run(self, project_root: Path, prompt: str) -> str:
        argv = [self.executable, "--in", str(project_root.resolve())]
        if self.model:
            argv.extend(["--model", self.model])
        if self.reasoning:
            argv.extend(["--reasoning", self.reasoning])
        argv.extend(["-z", prompt])
        return LocalShellTool(project_root, environment=self.environment).run(
            argv,
            timeout_seconds=900,
        )

    def implement(
        self,
        project_root: Path,
        specification: str,
        failure: str | None = None,
    ) -> str:
        prompt = (
            "You are the implementation executor for a competition project. "
            "Work directly in the current project directory. Implement the requested "
            "slice completely, including tests. Inspect existing files first, make the "
            "smallest coherent changes, and do not publish or push anything.\n\n"
            f"SPECIFICATION:\n{specification}"
        )
        if failure:
            prompt += f"\n\nPRIOR FAILURE:\n{failure}"
        return self._run(project_root, prompt)

    def repair(self, project_root: Path, specification: str, failure: str) -> str:
        return self.implement(project_root, specification, failure=failure)


class ClaudeCodeImplementer:
    """A real coding agent, writing real files in the project directory.

    The Hermes path stays the hosted runtime's implementer. This one exists so
    a mission can be implemented wherever Joust is actually running, and so
    that the provider behind a ChangeSet is a fact the database carries rather
    than an assumption.

    Edits are accepted automatically inside the project root and nowhere else;
    the agent gets no permission to reach outside it.
    """

    provider = "claude-code-cli"

    def __init__(
        self,
        *,
        executable: str = "claude",
        model: str = "default",
        timeout_seconds: float = 1800.0,
        environment: Mapping[str, str] | None = None,
    ):
        self.executable = executable
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.environment = dict(environment) if environment is not None else dict(os.environ)
        self.last_output = ""

    def set_environment(self, environment: Mapping[str, str]) -> None:
        # Deliberately ignored: project commands run with a filtered
        # environment, but the coding agent needs its own credentials to run
        # at all. Mixing the two is what leaks a token into a build command.
        return None

    def _run(self, project_root: Path, prompt: str) -> str:
        resolved = shutil.which(self.executable)
        if resolved is None:
            raise BuildLoopError(
                f"IMPLEMENTATION_PROVIDER_UNAVAILABLE: {self.executable} is not on PATH"
            )
        argv = [
            resolved,
            "-p",
            prompt,
            "--permission-mode",
            "acceptEdits",
            "--add-dir",
            str(project_root.resolve()),
        ]
        if self.model and self.model != "default":
            argv.extend(["--model", self.model])
        try:
            result = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
                cwd=str(project_root.resolve()),
                env={**self.environment, "CLAUDE_CODE_ENTRYPOINT": "joust"},
            )
        except subprocess.TimeoutExpired as error:
            raise BuildLoopError(
                f"IMPLEMENTATION_PROVIDER_TIMEOUT: no result in {self.timeout_seconds:.0f}s"
            ) from error
        if result.returncode != 0:
            raise BuildLoopError(
                "IMPLEMENTATION_PROVIDER_FAILED: "
                + ((result.stderr or result.stdout).strip()[:500] or f"exit {result.returncode}")
            )
        self.last_output = result.stdout
        return result.stdout

    def implement(
        self,
        project_root: Path,
        specification: str,
        failure: str | None = None,
    ) -> str:
        prompt = (
            "You are implementing a competition entry. Work only inside the current "
            "directory. Implement the specification completely, with tests that actually "
            "exercise the behaviour. Inspect what already exists before writing. Do not "
            "invent APIs, credentials or telemetry, and do not push, publish or deploy "
            "anything.\n\n"
            f"SPECIFICATION:\n{specification}"
        )
        if failure:
            prompt += (
                "\n\nA previous attempt failed. Read this output, find the root cause, "
                "and fix it:\n" + failure
            )
        return self._run(project_root, prompt)

    def repair(self, project_root: Path, specification: str, failure: str) -> str:
        prompt = (
            "A verification command just failed in this project. Diagnose it from the "
            "output below and the code, state the root cause, apply the smallest repair "
            "that fixes it, and do not weaken or delete tests to make them pass.\n\n"
            f"ORIGINAL SPECIFICATION:\n{specification}\n\nFAILURE OUTPUT:\n{failure}"
        )
        return self._run(project_root, prompt)


class RealBuildLoop:
    """Build a mission-owned project, record a change set, and prove reproducibility."""

    def __init__(
        self,
        database: Database,
        artifact_root: str | Path,
        *,
        github: ProjectBootstrap | None = None,
    ):
        self.database = database
        self.artifact_root = Path(artifact_root)
        self.github = github

    def _snapshot(
        self, target: ProjectTarget, git: LocalGitTool, *, dirty: bool
    ) -> RepositorySnapshot:
        snapshot = RepositorySnapshot(
            mission_id=target.mission_id,
            project_target_id=target.id,
            repository_url=target.repository_url,
            branch=target.working_branch,
            commit_sha=git.current_revision(),
            dirty=dirty,
        )
        self.database.save_repository_snapshot(snapshot)
        return snapshot

    def _run_commands(
        self,
        target: ProjectTarget,
        commands: Sequence[tuple[str, list[str]]],
        git: LocalGitTool,
    ) -> tuple[bool, str]:
        shell = git.shell
        failure = ""
        for phase, argv in commands:
            started = datetime.now(UTC)
            output = ""
            passed = False
            error = None
            exit_code = 0
            try:
                output = shell.run(argv, timeout_seconds=300)
                passed = True
            except (RuntimeError, TimeoutError) as exc:
                error = str(exc)
                failure = error
                exit_code = 1
            log_path = self.artifact_root / str(target.mission_id) / "build" / f"{phase}.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(output or error or "", encoding="utf-8")
            run = BuildRun(
                mission_id=target.mission_id,
                project_target_id=target.id,
                commit_sha=git.current_revision(),
                command=list(argv),
                phase=phase,
                exit_code=exit_code,
                log_path=str(log_path),
                passed=passed,
                started_at=started,
                finished_at=datetime.now(UTC),
                error=error,
            )
            self.database.save_build_run(run)
            self.database.append_event(
                target.mission_id,
                "BUILD_RUN_RECORDED",
                {"build_run_id": str(run.id), "phase": phase, "passed": passed},
            )
            if not passed:
                return False, failure
        return True, ""

    def _reproduce(
        self,
        target: ProjectTarget,
        commit_sha: str,
        commands: Sequence[tuple[str, list[str]]],
        *,
        environment: Mapping[str, str],
    ) -> None:
        """Run the validated commit from a clean clone, never the working tree."""

        source = Path(target.local_path).resolve()
        with tempfile.TemporaryDirectory(prefix="joust-reproduce-") as temporary:
            clone = Path(temporary) / "project"
            shell = LocalShellTool(clone, environment=environment)
            shell.run(["git", "clone", "--no-local", str(source), str(clone)], timeout_seconds=60)
            shell.run(["git", "checkout", "--detach", commit_sha], timeout_seconds=30)
            for phase, argv in commands:
                started = datetime.now(UTC)
                output = ""
                passed = False
                error = None
                exit_code = 0
                try:
                    output = shell.run(argv, timeout_seconds=300)
                    passed = True
                except (RuntimeError, TimeoutError) as exc:
                    error = str(exc)
                    exit_code = 1
                log_path = (
                    self.artifact_root / str(target.mission_id) / "build" / f"reproduce-{phase}.log"
                )
                log_path.parent.mkdir(parents=True, exist_ok=True)
                log_path.write_text(output or error or "", encoding="utf-8")
                run = BuildRun(
                    mission_id=target.mission_id,
                    project_target_id=target.id,
                    commit_sha=commit_sha,
                    command=list(argv),
                    phase=f"reproduce_{phase}",
                    exit_code=exit_code,
                    log_path=str(log_path),
                    passed=passed,
                    started_at=started,
                    finished_at=datetime.now(UTC),
                    error=error,
                )
                self.database.save_build_run(run)
                self.database.append_event(
                    target.mission_id,
                    "BUILD_REPRODUCTION_RECORDED",
                    {"build_run_id": str(run.id), "phase": phase, "passed": passed},
                )
                if not passed:
                    raise BuildLoopError(
                        f"clean-clone reproduction failed in {phase}: {error or 'unknown error'}"
                    )

    def run(
        self,
        target: ProjectTarget,
        specification: str,
        implementer: Implementer,
        *,
        max_repairs: int = 1,
        allow_no_changes: bool = False,
    ) -> ChangeSet:
        if max_repairs < 0:
            raise ValueError("max_repairs cannot be negative")
        root = Path(target.local_path).resolve()
        environment = project_environment(target.environment_allowlist)
        if not root.exists() and target.mode.value == "existing_repo" and target.repository_url:
            if self.github is None:
                raise BuildLoopError(
                    "GitHub checkout is missing; configure a GitHub adapter or provide a local clone"
                )
            root.parent.mkdir(parents=True, exist_ok=True)
            self.github.clone(target.repository_url, str(root))
        root.mkdir(parents=True, exist_ok=True)
        git_workspace = GitWorkspace(root, environment=environment)
        git_workspace.initialize(default_branch=target.default_branch)
        git = LocalGitTool(root, shell=git_workspace.shell)
        if git.changed_files():
            raise BuildLoopError("project workspace is dirty; refusing to overwrite user changes")
        try:
            base_sha = git.current_revision()
        except RuntimeError:
            (root / ".joust").mkdir(parents=True, exist_ok=True)
            (root / ".joust" / ".keep").write_text("", encoding="utf-8")
            base_sha = git_workspace.checkpoint("Initialize competition project workspace")
        target.base_commit_sha = base_sha
        branch = target.working_branch or f"joust/{target.mission_id}"
        target.working_branch = branch
        self.database.save_project_target(target)
        if git.current_branch() != branch:
            if git.branch_exists(branch):
                git.switch_branch(branch)
            else:
                git.create_branch(branch, target.default_branch)
        self._snapshot(target, git, dirty=False)

        commands = [
            *(("install", command) for command in target.install_commands),
            *(("lint", command) for command in target.lint_commands),
            *(("build", command) for command in target.build_commands),
            *(("test", command) for command in target.test_commands),
            *(("run", command) for command in target.run_commands),
        ]
        if not commands:
            raise BuildLoopError(
                "project target must declare an install, lint, build, test, or run command"
            )
        validate_project_commands([command for _, command in commands])

        set_environment = getattr(implementer, "set_environment", None)
        if callable(set_environment):
            set_environment(environment)
        implementer.implement(root, specification)
        has_changes = bool(git.changed_files())
        commit_sha = git_workspace.checkpoint("Implement competition project slice")
        diff = git.commit_diff(commit_sha) if has_changes else ""
        change_set = ChangeSet(
            mission_id=target.mission_id,
            project_target_id=target.id,
            base_sha=base_sha,
            generated_by=_provenance(implementer),
            diff_hash=hashlib.sha256(diff.encode()).hexdigest(),
            files=git.commit_changed_files(commit_sha) if has_changes else [],
            commit_sha=commit_sha,
            status="committed",
            verification_only=allow_no_changes and not has_changes,
        )
        self.database.save_change_set(change_set)
        for attempt in range(max_repairs + 1):
            passed, failure = self._run_commands(target, commands, git)
            if passed:
                try:
                    self._reproduce(target, commit_sha, commands, environment=environment)
                except BuildLoopError as exc:
                    passed = False
                    failure = str(exc)
                else:
                    # Mark the commit validated only long enough to let the
                    # review inspect the actual changed files and evidence.
                    # A blocker sends the same bounded repair loop around
                    # again; it is never silently downgraded to a warning.
                    change_set.status = "validated"
                    self.database.save_change_set(change_set)
                    review = review_project_change(
                        target,
                        change_set,
                        self.database.list_build_runs(target.mission_id),
                    )
                    self.database.append_event(
                        target.mission_id,
                        "PROJECT_REVIEW_COMPLETED",
                        review,
                    )
                    blockers = [str(item) for item in review["blocking_findings"]]
                    if not blockers:
                        target.final_commit_sha = commit_sha
                        self.database.save_project_target(target)
                        self.database.append_event(
                            target.mission_id,
                            "PROJECT_BUILD_VALIDATED",
                            {
                                "change_set_id": str(change_set.id),
                                "commit_sha": commit_sha,
                                "attempt": attempt + 1,
                            },
                        )
                        return change_set
                    passed = False
                    failure = "project review blocked the change set: " + "; ".join(blockers)
            if attempt >= max_repairs:
                change_set.status = (
                    "review_failed"
                    if failure.startswith("project review blocked")
                    else "failed_validation"
                )
                self.database.save_change_set(change_set)
                raise BuildLoopError(
                    f"project validation failed after {attempt + 1} attempt(s): {failure}"
                )
            repair = getattr(implementer, "repair", None)
            if not callable(repair):
                change_set.status = (
                    "review_failed"
                    if failure.startswith("project review blocked")
                    else "failed_validation"
                )
                self.database.save_change_set(change_set)
                raise BuildLoopError(
                    "project validation failed and implementer has no repair method"
                )
            repair(root, specification, failure)
            commit_sha = git_workspace.checkpoint("Repair competition project validation failure")
            change_set.commit_sha = commit_sha
            diff = git.commit_diff(commit_sha)
            change_set.diff_hash = hashlib.sha256(diff.encode()).hexdigest()
            change_set.files = sorted(
                set(change_set.files) | set(git.commit_changed_files(commit_sha))
            )
            change_set.status = "repaired"
            self.database.save_change_set(change_set)
        raise AssertionError("unreachable build loop state")
