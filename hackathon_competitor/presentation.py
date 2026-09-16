"""The boundary between Joust's durable state and product language.

The mission record remains deliberately detailed. This module is the one
place that turns that record into something suitable for a normal Plow Chat
reply. Technical details are available only when the operator explicitly asks
for them.
"""

from __future__ import annotations

import re
from enum import StrEnum
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Mapping

from .models import GitHubConnectionStatus, MissionState


class PresentationMode(StrEnum):
    NORMAL = "normal"
    DETAILS = "details"


_DETAILS_PHRASES = (
    "show details",
    "show debug",
    "show debug info",
    "show logs",
    "where is it stored",
    "which branch",
    "show technical details",
    "show technical info",
    "detalhes",
    "debug",
    "logs",
    "onde está armazenado",
    "onde esta armazenado",
    "qual branch",
    "qual é a branch",
    "qual e a branch",
    "detalhes técnicos",
    "detalhes tecnicos",
)


def presentation_mode(request: str) -> PresentationMode:
    """Choose details only for an explicit technical request."""

    normalized = " ".join(request.casefold().split())
    if any(phrase in normalized for phrase in _DETAILS_PHRASES):
        return PresentationMode.DETAILS
    return PresentationMode.NORMAL


def _project_name(project: Mapping[str, Any] | None) -> str | None:
    if not project:
        return None
    name = project.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    path = project.get("path")
    if not isinstance(path, str) or not path.strip():
        return None
    # A mission can run on either Windows or Linux. Pure paths avoid touching
    # the filesystem and make the name safe to expose as a product label.
    for candidate in (PurePosixPath(path).name, PureWindowsPath(path).name):
        if candidate and candidate not in {".", "/", "\\"}:
            return candidate
    return None


def _public_state(value: Any) -> str:
    state = str(value or "").upper()
    if state == MissionState.PAUSED.value:
        return "paused"
    if state == MissionState.CANCELLED.value:
        return "cancelled"
    if state == MissionState.BLOCKED.value:
        return "blocked"
    if state in {MissionState.READY_FOR_SUBMISSION.value, MissionState.SUBMITTED.value}:
        return "ready"
    if state == MissionState.FAILED.value:
        return "blocked"
    return "in progress"


def public_mission_facts(
    facts: Mapping[str, Any],
    *,
    github: GitHubConnectionStatus | Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return facts safe to place in a normal model prompt.

    Paths, UUIDs, branch names, raw commands, and implementation fields are
    intentionally omitted. A real repository URL is retained because it is a
    user asset rather than an internal location.
    """

    project = facts.get("project")
    project_data: dict[str, Any] | None = None
    if isinstance(project, Mapping):
        repository_url = project.get("repository_url")
        project_data = {
            "name": _project_name(project),
            "location": "repository" if repository_url else "local",
            "repository_url": repository_url if isinstance(repository_url, str) else None,
            "tests_passed": project.get("tests_passed"),
            "git_history_saved": bool(project.get("git_history_saved")),
        }

    public: dict[str, Any] = {
        "competition": facts.get("competition"),
        "competition_url": facts.get("competition_url"),
        "state": _public_state(facts.get("state")),
        "deadline": facts.get("deadline_at"),
        "blockers": facts.get("blockers", []),
        "project": project_data,
        "tasks_total": facts.get("tasks_total"),
        "tasks_succeeded": facts.get("tasks_succeeded"),
        "tests_passed": facts.get("tests_passed"),
        "evidence_saved": bool(facts.get("evidence_count")),
    }
    if github is not None:
        if isinstance(github, Mapping):
            public["github"] = {
                "connected": bool(github.get("connected")),
                "login": github.get("login"),
                "can_push_to_target": github.get("can_push_to_target"),
            }
        else:
            public["github"] = {
                "connected": github.connected,
                "login": github.login,
                "can_push_to_target": github.can_push_to_target,
            }
    return public


def render_github_connection(status: GitHubConnectionStatus | Mapping[str, Any]) -> str:
    """Render an installation-scoped GitHub observation in product language."""

    if isinstance(status, Mapping):
        connected = bool(status.get("connected"))
        login = status.get("login")
        can_push = status.get("can_push_to_target")
    else:
        connected = status.connected
        login = status.login
        can_push = status.can_push_to_target
    if not connected:
        return (
            "GitHub isn't connected yet.\n\n"
            "Connect a GitHub account to let me create repositories, push code, "
            "and open pull requests."
        )
    if isinstance(login, str) and login:
        if can_push is False:
            return f"GitHub is connected as {login}, but that account can't push to this repository."
        return f"GitHub connected: {login}."
    return "GitHub is connected."


def render_project_ready(
    *,
    name: str,
    tests_passed: int | None = None,
    repository_url: str | None = None,
    github: GitHubConnectionStatus | Mapping[str, Any] | None = None,
) -> str:
    """Render a concise ready-project response."""

    lines = [f"{name} is ready.", ""]
    if tests_passed is not None:
        lines.append(f"✓ {tests_passed} tests pass")
    lines.extend(("✓ Git history is saved", "✓ The project is preserved"))
    if github is not None:
        lines.extend(("", render_github_connection(github)))
    if repository_url:
        lines.extend(("", f"Repository: {repository_url}"))
    else:
        lines.extend(("", "It hasn't been published yet."))
    return "\n".join(lines)


def render_answer(text: str, *, mode: PresentationMode = PresentationMode.NORMAL) -> str:
    """Redact infrastructure language from a normal answer.

    This is a final safety net for provider text. The model prompt already
    receives redacted facts, but provider output is still treated as untrusted.
    """

    if mode is PresentationMode.DETAILS:
        return text.strip()
    rendered = text.strip()
    rendered = re.sub(
        r"`?(?:/var/lib/hermes|/opt/|/var/run/|/etc/s6-overlay/)[^`\s),]*`?",
        "the local project",
        rendered,
        flags=re.IGNORECASE,
    )
    rendered = re.sub(
        r"\bthe\s+project\s+lives?\s+at\s+the\s+local\s+project(?:\s+in\s+Joust)?",
        "The project is local to Joust.",
        rendered,
        flags=re.IGNORECASE,
    )
    rendered = re.sub(
        r"\b(?:galahad-agent(?:-\d+)?|joust-[0-9a-f]{8,}(?:-[0-9a-f-]+)?)\b",
        "Joust",
        rendered,
        flags=re.IGNORECASE,
    )
    rendered = re.sub(
        r"\bthe\s+project\s+lives?\s+at\s+the\s+local\s+project(?:\s+in\s+Joust)?",
        "The project is local to Joust.",
        rendered,
        flags=re.IGNORECASE,
    )
    rendered = re.sub(
        r"\b(?:MissionOrchestrator|MissionLifecycleService|ProjectTarget|GitHubCliAdapter|TaskEngine|StateMachine)\b",
        "Joust",
        rendered,
        flags=re.IGNORECASE,
    )
    rendered = re.sub(
        r"\b(?:orchestrator(?:-level)?|orchestration)\b|cancel\(\)",
        "Joust",
        rendered,
        flags=re.IGNORECASE,
    )
    rendered = re.sub(
        r"\b(?:branch|ref)\s*[:=]?\s*[^\s.,;]+",
        "the project state",
        rendered,
        flags=re.IGNORECASE,
    )
    rendered = re.sub(
        r"(?im)^\s*git\s+history\s+on\s+(?:the\s+)?project\s+state\s*$",
        "Git history is saved.",
        rendered,
    )
    rendered = re.sub(
        r"\b(?:gh\s+auth(?:entication)?|docker\s+(?:compose|run|exec)|git\s+(?:status|branch|log|rev-parse))\b[^.\n]*",
        "GitHub connection",
        rendered,
        flags=re.IGNORECASE,
    )
    rendered = re.sub(
        r"\b(?:filesystem|file system) on (?:the )?(?:cloud )?(?:agent|container)[^.\n]*",
        "local to Joust",
        rendered,
        flags=re.IGNORECASE,
    )
    rendered = re.sub(
        r"\b(?:the )?project\s+lives?\s+on\s+(?:this\s+)?(?:cloud\s+)?(?:agent|container)[^\.\n]*filesystem",
        "the project is local to Joust",
        rendered,
        flags=re.IGNORECASE,
    )
    rendered = re.sub(
        r"\b(?:filesystem|file system)\b[^\.\n]*",
        "the project is local to Joust",
        rendered,
        flags=re.IGNORECASE,
    )
    rendered = re.sub(
        r"(?im)^\s*(?:path|location)\s*:\s*the\s+local\s+project\s*$",
        "The project is local to Joust.",
        rendered,
    )
    rendered = re.sub(
        r"\b(?:gh|GitHub CLI)\s+(?:is\s+)?(?:authenticated|logged\s+in)\s+as\s+([\w.-]+)",
        r"GitHub connected: \1",
        rendered,
        flags=re.IGNORECASE,
    )
    rendered = re.sub(
        r"\b(?:your|the)\s+GitHub\s+account\b",
        "the connected GitHub account",
        rendered,
        flags=re.IGNORECASE,
    )
    rendered = re.sub(
        r"\b(?:internal\s+(?:CLI|command|wiring|state[- ]machine)|database\s+transition|implementation\s+(?:gap|detail|explanation))\b[^.\n]*",
        "Joust",
        rendered,
        flags=re.IGNORECASE,
    )
    rendered = re.sub(
        r"\b(?:BUILDING|VALIDATING|OPTIMIZING|SUBMISSION_PREP|READY_FOR_SUBMISSION|ACTIVE|COMPLETED)\b",
        "in progress",
        rendered,
    )
    rendered = re.sub(
        r"\b[0-9a-f]{8}-[0-9a-f-]{27,}\b",
        "the mission",
        rendered,
        flags=re.IGNORECASE,
    )
    rendered = re.sub(r"\bJoust(?:\s+Joust)+\b", "Joust", rendered)
    rendered = re.sub(
        r"The project is local to Joust\.\s+in Joust\.",
        "The project is local to Joust.",
        rendered,
        flags=re.IGNORECASE,
    )
    lines = [re.sub(r"[ \t]{2,}", " ", line).strip() for line in rendered.splitlines()]
    compact: list[str] = []
    for line in lines:
        if not line and compact and not compact[-1]:
            continue
        compact.append(line)
    return "\n".join(compact).strip()


__all__ = [
    "PresentationMode",
    "presentation_mode",
    "public_mission_facts",
    "render_answer",
    "render_github_connection",
    "render_project_ready",
]
