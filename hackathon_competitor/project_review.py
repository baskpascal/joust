from __future__ import annotations

import re
from pathlib import Path

from .models import BuildRun, ChangeSet, ProjectTarget

_SECRET_PATTERNS = (
    re.compile(r"PLOW_AGENT_TOKEN\s*[:=]", re.IGNORECASE),
    re.compile(r"(?:sk|ghp|github_pat)_[A-Za-z0-9_\-]{20,}"),
    re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----"),
)


def review_project_change(
    target: ProjectTarget,
    change_set: ChangeSet,
    build_runs: list[BuildRun],
) -> dict[str, object]:
    """Review the actual changed files and build evidence, not a synthetic demo string."""

    root = Path(target.local_path).resolve()
    findings: list[str] = []
    blockers: list[str] = []
    if change_set.mission_id != target.mission_id:
        blockers.append("change set belongs to a different mission")
    if change_set.project_target_id != target.id:
        blockers.append("change set belongs to a different project target")
    changed = []
    for relative in change_set.files:
        path = (root / relative).resolve()
        if root not in path.parents and path != root:
            blockers.append(f"changed path escapes project root: {relative}")
            continue
        changed.append(relative)
        if path.is_file():
            content = path.read_text(encoding="utf-8", errors="replace")
            if any(pattern.search(content) for pattern in _SECRET_PATTERNS):
                blockers.append(f"possible secret in changed file: {relative}")

    if not changed:
        blockers.append("validated change set contains no changed files")
    if not any(Path(item).name.lower().startswith("test") for item in changed):
        findings.append("no changed test file was found")
    if not any(Path(item).name.lower() == "readme.md" for item in changed):
        findings.append("no changed README was found")
    test_runs = [run for run in build_runs if run.phase in {"test", "reproduce_test"}]
    if not test_runs or not all(run.passed for run in test_runs):
        blockers.append("project test evidence is missing or failed")
    if change_set.status != "validated":
        blockers.append(f"change set is not validated: {change_set.status}")
    return {
        "passed": not blockers,
        "changed_files": changed,
        "findings": findings,
        "blocking_findings": blockers,
        "test_runs": len(test_runs),
        "commit_sha": change_set.commit_sha,
        "diff_hash": change_set.diff_hash,
    }
