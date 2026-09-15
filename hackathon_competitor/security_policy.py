"""Whether a proposed command may run at all, before any approval UI exists.

A live incident is what this module exists to prevent: asked why a
competition URL was unreachable, an agent proposed `cat /var/lib/hermes/.env`,
`env | grep ...`, and `find /etc/ssl ...` as its own diagnosis, and a user's
`/deny` was answered "No pending command to deny" while the agent kept going.
Two failures compound there — an approval channel that lost the request, and
a command that should never have reached an approval prompt in the first
place, because there is no legitimate reason a connectivity check needs to
read a credential file or dump the environment.

This module is the second failure's fix: a command is classified before it is
ever shown to anyone, and a forbidden one is rejected outright rather than
rendered as something a user could approve. `build_loop.validate_project_commands`
already rejects a *credential-shaped argument* appearing in a project's own
build commands; this is the sibling concern — a command whose *target* is a
secret, a key, or the whole environment, regardless of what its arguments look
like. Both are enforced; neither substitutes for the other.

A user should never have to recognise `.env`, `plow-credentials`, an SSH key
path, or `env | grep` as dangerous. That recognition happens here, once, so
nobody downstream has to make it themselves under pressure in a chat window.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

# Path fragments that name a place credentials or private key material live.
# Matched case-insensitively against the full command text, not just argv
# tokens, because a shell command is often one string ("cat a && env | grep b").
_FORBIDDEN_PATH_FRAGMENTS = (
    ".env",
    "plow-credentials",
    "plow_credentials",
    ".ssh/",
    "id_rsa",
    "id_ed25519",
    "authorized_keys",
    ".pem",
    ".pfx",
    ".p12",
    ".kube/config",
    ".aws/credentials",
    ".netrc",
    "/proc/self/environ",
    "/proc/1/environ",
)

# Name-shaped patterns: an argument or path component that looks like a
# secret by its *name*, independent of any specific value.
_FORBIDDEN_NAME_PATTERN = re.compile(
    r"(?:^|[^A-Z0-9])(?:[A-Z0-9_]*_)?(?:TOKEN|API_KEY|SECRET|PASSWORD|PASSWD|"
    r"PRIVATE_KEY|CLIENT_SECRET|AUTH_HEADER|AUTHORIZATION|SET-COOKIE|COOKIE)"
    r"(?:[^A-Z0-9]|$)",
    re.IGNORECASE,
)

# Commands whose ordinary effect is "print everything in the environment" —
# not one named variable, the whole table. `printenv PATH` names exactly one
# variable and is not this; bare `env`, bare `printenv`, or either piped into
# a filter (grep, awk, ...) with no single variable named, is exactly this.
_ENV_DUMP_INVOCATION = re.compile(r"(?:^|[|;&]\s*)(env|printenv|set)\b\s*(.*)$", re.MULTILINE)
_SINGLE_VARIABLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SHELL_FLAG = re.compile(r"^-")


def _is_environment_dump(text: str) -> bool:
    for match in _ENV_DUMP_INVOCATION.finditer(text):
        remainder = match.group(2).strip()
        if not remainder:
            return True  # bare env / printenv / set: the whole table
        # `env NAME=value command...` sets one variable for a subcommand;
        # `set -e` is a shell option, not a variable dump; `printenv NAME`
        # (and only NAME) names exactly one variable to read.
        first_token = remainder.split()[0]
        if _SHELL_FLAG.match(first_token) or "=" in first_token:
            continue
        if match.group(1) == "printenv" and _SINGLE_VARIABLE_NAME.match(first_token):
            if len(remainder.split()) == 1:
                continue
        return True
    return False


# Directories where certificate and key material live. Reading *into* them
# with a shell command (find/grep/ls/cat) is forbidden; the safe network
# diagnostics capability in capabilities/network_diagnostics.py performs the
# equivalent check (does this host's certificate validate?) as a direct,
# read-only library call that never has shell access to these paths at all,
# and is the tool a diagnosis should reach for instead.
_KEY_MATERIAL_DIRECTORY_PATTERN = re.compile(
    r"(?:/etc/ssl|/etc/pki|/etc/pki/tls|/etc/letsencrypt|/\.ssh)(?:/|\b)",
    re.IGNORECASE,
)
_TRAVERSAL_COMMAND_PATTERN = re.compile(r"^\s*(find|grep|ls|cat|tail|head|rg)\b")


@dataclass(frozen=True)
class CommandVerdict:
    allowed: bool
    category: str
    reason: str


def _command_text(command: str | Sequence[str]) -> str:
    return command if isinstance(command, str) else " ".join(command)


def classify_command(command: str | Sequence[str]) -> CommandVerdict:
    """Classify one command's *target*, before it is ever shown to a user.

    Accepts either a shell string (an agent's own free-form command) or an
    argv list (Joust's own explicit commands), since both shapes occur in
    this codebase and a pipeline (`env | grep TOKEN`) only exists as a
    string.
    """

    text = _command_text(command)
    lowered = text.lower()

    for fragment in _FORBIDDEN_PATH_FRAGMENTS:
        if fragment in lowered:
            return CommandVerdict(
                allowed=False,
                category="secret_file_access",
                reason=f"targets a credential or key path ({fragment})",
            )

    if _FORBIDDEN_NAME_PATTERN.search(text):
        return CommandVerdict(
            allowed=False,
            category="credential_pattern",
            reason="references a secret-shaped name (token, key, secret, password, "
            "auth header, or cookie)",
        )

    if _is_environment_dump(text):
        return CommandVerdict(
            allowed=False,
            category="environment_dump",
            reason="dumps the process environment rather than reading one declared "
            "non-secret variable",
        )

    if _TRAVERSAL_COMMAND_PATTERN.match(lowered.strip()) and _KEY_MATERIAL_DIRECTORY_PATTERN.search(
        lowered
    ):
        return CommandVerdict(
            allowed=False,
            category="key_material_directory",
            reason="inspects a certificate/key directory directly; use the network "
            "diagnostics capability instead",
        )

    return CommandVerdict(allowed=True, category="allowed", reason="")


def require_safe_command(command: str | Sequence[str]) -> None:
    """Raise if a command is forbidden. For call sites that cannot proceed at all."""

    verdict = classify_command(command)
    if not verdict.allowed:
        raise ForbiddenCommand(verdict)


class ForbiddenCommand(PermissionError):
    def __init__(self, verdict: CommandVerdict):
        self.verdict = verdict
        super().__init__(f"{verdict.category}: {verdict.reason}")


__all__ = [
    "CommandVerdict",
    "ForbiddenCommand",
    "classify_command",
    "require_safe_command",
]
