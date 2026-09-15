"""Where the Plow credential is, without ever asking a configured operator.

An operator who already set `PLOW_CREDENTIALS_PATH` (or the same key in a
`.env` next to the checkout) must never be asked "where is your credential?" —
Joust already has the contract; it just has to read it in a fixed, honest
order and never open the file it names.
"""

from __future__ import annotations

from pathlib import Path

from hackathon_competitor.credentials import (
    MISSING_CREDENTIAL_MESSAGE,
    credential_exists,
    resolve_credential_path,
)


def test_credential_path_from_env(tmp_path):
    configured = tmp_path / "somewhere" / "credentials"
    resolved = resolve_credential_path(
        repository_root=tmp_path, environment={"PLOW_CREDENTIALS_PATH": str(configured)}
    )
    assert resolved == configured


def test_credential_path_fallback_local(tmp_path):
    resolved = resolve_credential_path(repository_root=tmp_path, environment={})
    assert resolved == tmp_path / "plow-credentials"


def test_credential_path_expands_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    resolved = resolve_credential_path(
        repository_root=tmp_path, environment={"PLOW_CREDENTIALS_PATH": "~/.plow/credentials"}
    )
    assert resolved == tmp_path / ".plow" / "credentials"


def test_credential_path_cli_argument_wins_over_everything(tmp_path):
    explicit = tmp_path / "explicit-credentials"
    resolved = resolve_credential_path(
        repository_root=tmp_path,
        cli_path=str(explicit),
        environment={"PLOW_CREDENTIALS_PATH": str(tmp_path / "env-credentials")},
    )
    assert resolved == explicit


def test_credential_path_falls_back_to_dotenv_value(tmp_path):
    (tmp_path / ".env").write_text(
        "AGENT_ID=galahad-hackathon\nPLOW_CREDENTIALS_PATH=./from-dotenv\n", encoding="utf-8"
    )
    resolved = resolve_credential_path(repository_root=tmp_path, environment={})
    assert resolved == Path("from-dotenv")


def test_env_var_takes_priority_over_dotenv(tmp_path):
    (tmp_path / ".env").write_text("PLOW_CREDENTIALS_PATH=./from-dotenv\n", encoding="utf-8")
    resolved = resolve_credential_path(
        repository_root=tmp_path, environment={"PLOW_CREDENTIALS_PATH": "./from-env"}
    )
    assert resolved == Path("from-env")


def test_credential_resolver_never_reads_secret_content(tmp_path):
    """Resolution must work even when the credential holds unreadable garbage.

    If this ever opened the file, invalid bytes here would raise before the
    assertion could even run.
    """

    credential = tmp_path / "plow-credentials"
    credential.write_bytes(b"\xff\xfe\x00secret-token-bytes")
    resolved = resolve_credential_path(repository_root=tmp_path, environment={})
    assert resolved == credential
    assert credential_exists(resolved)


def test_missing_credential_returns_actionable_setup():
    assert "plow-agents mint" in MISSING_CREDENTIAL_MESSAGE
    assert "Where is your credential" not in MISSING_CREDENTIAL_MESSAGE


def test_configured_credential_does_not_prompt_user(tmp_path):
    """A configured, existing credential resolves silently: no missing-setup text."""

    credential = tmp_path / "plow-credentials"
    credential.write_text("token", encoding="utf-8")
    resolved = resolve_credential_path(repository_root=tmp_path, environment={})
    assert credential_exists(resolved)
