from __future__ import annotations

import hashlib
import tempfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from .models import BuildRun, ChangeSet, ProjectTarget, RepositorySnapshot
from .storage import Database
from .tool_gateway import LocalGitTool, LocalShellTool
from .workspace import GitWorkspace


class BuildLoopError(RuntimeError):
    pass


class Implementer(Protocol):
    def implement(self, project_root: Path, specification: str, failure: str | None = None) -> str: ...


class RepairableImplementer(Implementer, Protocol):
    def repair(self, project_root: Path, specification: str, failure: str) -> str: ...


class RealBuildLoop:
    """Build a mission-owned project, record a change set, and prove reproducibility."""

    def __init__(self, database: Database, artifact_root: str | Path):
        self.database = database
        self.artifact_root = Path(artifact_root)

    def _snapshot(self, target: ProjectTarget, git: LocalGitTool, *, dirty: bool) -> RepositorySnapshot:
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
    ) -> None:
        """Run the validated commit from a clean clone, never the working tree."""

        source = Path(target.local_path).resolve()
        with tempfile.TemporaryDirectory(prefix="galahad-reproduce-") as temporary:
            clone = Path(temporary) / "project"
            shell = LocalShellTool(clone)
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
                    self.artifact_root
                    / str(target.mission_id)
                    / "build"
                    / f"reproduce-{phase}.log"
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
    ) -> ChangeSet:
        root = Path(target.local_path).resolve()
        root.mkdir(parents=True, exist_ok=True)
        git_workspace = GitWorkspace(root)
        git_workspace.initialize(default_branch=target.default_branch)
        git = LocalGitTool(root)
        if git.changed_files():
            raise BuildLoopError("project workspace is dirty; refusing to overwrite user changes")
        try:
            base_sha = git.current_revision()
        except RuntimeError:
            (root / ".galahad").mkdir(parents=True, exist_ok=True)
            (root / ".galahad" / ".keep").write_text("", encoding="utf-8")
            base_sha = git_workspace.checkpoint("Initialize competition project workspace")
        branch = target.working_branch or f"galahad/{target.mission_id}"
        target.working_branch = branch
        self.database.save_project_target(target)
        if git.current_branch() != branch:
            if git.branch_exists(branch):
                git.switch_branch(branch)
            else:
                git.create_branch(branch, target.default_branch)
        self._snapshot(target, git, dirty=False)

        commands = [
            *(('install', command) for command in target.install_commands),
            *(('build', command) for command in target.build_commands),
            *(('test', command) for command in target.test_commands),
        ]
        if not commands:
            raise BuildLoopError("project target must declare an install, build, or test command")

        implementer.implement(root, specification)
        commit_sha = git_workspace.checkpoint("Implement competition project slice")
        diff = git.commit_diff(commit_sha)
        change_set = ChangeSet(
            mission_id=target.mission_id,
            project_target_id=target.id,
            base_sha=base_sha,
            diff_hash=hashlib.sha256(diff.encode()).hexdigest(),
            files=git.commit_changed_files(commit_sha),
            commit_sha=commit_sha,
            status="committed",
        )
        self.database.save_change_set(change_set)
        for attempt in range(max_repairs + 1):
            passed, failure = self._run_commands(target, commands, git)
            if passed:
                self._reproduce(target, commit_sha, commands)
                change_set.status = "validated"
                self.database.save_change_set(change_set)
                self.database.append_event(
                    target.mission_id,
                    "PROJECT_BUILD_VALIDATED",
                    {"change_set_id": str(change_set.id), "commit_sha": commit_sha, "attempt": attempt + 1},
                )
                return change_set
            if attempt >= max_repairs:
                change_set.status = "failed_validation"
                self.database.save_change_set(change_set)
                raise BuildLoopError(f"project validation failed after {attempt + 1} attempt(s): {failure}")
            repair = getattr(implementer, "repair", None)
            if not callable(repair):
                raise BuildLoopError("project validation failed and implementer has no repair method")
            repair(root, specification, failure)
            commit_sha = git_workspace.checkpoint("Repair competition project validation failure")
            change_set.commit_sha = commit_sha
            change_set.files = sorted(
                set(change_set.files) | set(git.commit_changed_files(commit_sha))
            )
            change_set.status = "repaired"
            self.database.save_change_set(change_set)
        raise AssertionError("unreachable build loop state")
