"""Where the Plow line credential lives, and nothing about what is in it.

An operator asked, mid-release, why Joust would ever need to ask a person
where their credential is once `PLOW_CREDENTIALS_PATH` (or a `.env` next to
the checkout, the same thing Compose itself reads) is already configured.
The credential's *path* is not secret, and Joust already has an explicit
contract for it — `PLOW_CREDENTIALS_PATH`, falling back to
`./plow-credentials` — so resolving it is a matter of reading one named
variable in a fixed order, never a filesystem search, and the file itself
is never opened here: existence and mode can be checked without reading a
single byte of its contents.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

ENV_VAR = "PLOW_CREDENTIALS_PATH"
DEFAULT_RELATIVE_PATH = "plow-credentials"

MISSING_CREDENTIAL_MESSAGE = (
    "Joust needs a Plow line credential before it can start.\n\n"
    "Run:\n"
    "  plow-agents mint <line> --credential-file ~/.config/joust/plow-credentials\n\n"
    "Then retry."
)


def resolve_credential_path(
    *,
    repository_root: Path,
    cli_path: str | None = None,
    environment: Mapping[str, str] | None = None,
    dotenv_path: Path | None = None,
) -> Path:
    """The one path Joust should treat as "the configured credential".

    Resolution order: an explicit CLI argument, `PLOW_CREDENTIALS_PATH` in
    the process environment, the same key read from a `.env` file next to
    the checkout (what `docker compose` itself would read), and finally the
    documented `./plow-credentials` default. Every result is `~`-expanded.
    A caller that finds nothing at the resolved path should say so with
    `MISSING_CREDENTIAL_MESSAGE`, not search anywhere else for the token.
    """

    if cli_path:
        return Path(cli_path).expanduser()
    env = environment if environment is not None else os.environ
    configured = env.get(ENV_VAR, "").strip()
    if configured:
        return Path(configured).expanduser()
    dotenv_value = _read_dotenv_value(dotenv_path or repository_root / ".env", ENV_VAR)
    if dotenv_value:
        return Path(dotenv_value).expanduser()
    return (repository_root / DEFAULT_RELATIVE_PATH).expanduser()


def _read_dotenv_value(path: Path, key: str) -> str | None:
    """One `KEY=value` line, read as plain text. Never executed, never sourced."""

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    prefix = f"{key}="
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") or not stripped.startswith(prefix):
            continue
        value = stripped[len(prefix) :].strip().strip('"').strip("'")
        return value or None
    return None


def credential_exists(path: Path) -> bool:
    """Whether a regular file sits at `path`. Never opens or reads it."""

    return path.is_file()


__all__ = [
    "DEFAULT_RELATIVE_PATH",
    "ENV_VAR",
    "MISSING_CREDENTIAL_MESSAGE",
    "credential_exists",
    "resolve_credential_path",
]
