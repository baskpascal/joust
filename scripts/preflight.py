#!/usr/bin/env python3
"""Check this machine before `docker compose up`, and say what is wrong.

The Agent Index recorded three install attempts against Joust and zero
successes, with no log of why any of them stopped.  Everything Joust needs is
checkable in a second from a bare clone, so nobody should have to discover a
missing daemon or an unprotected token by watching a build fail.

Deliberately standalone: stdlib only, no project imports, no installed
dependencies.  It has to run the moment the clone finishes.

    python3 scripts/preflight.py

Exit code 0 means every blocking check passed.  Nothing here starts, builds,
or changes anything.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

REQUIRED_FREE_BYTES = 6 * 1024**3
CREDENTIAL_MODES = {0o400, 0o600}


@dataclass
class Check:
    name: str
    ok: bool
    blocking: bool = True
    detail: str = ""
    remedy: str = ""
    facts: dict[str, object] = field(default_factory=dict)


def _one_line(text: str) -> str:
    """Keep a check one line long; a wall of vendor output hides the verdict."""

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    return lines[0] if len(lines) == 1 else f"{lines[0]} […]"


def _run(command: list[str], timeout: float = 20.0) -> tuple[int, str]:
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False
        )
    except FileNotFoundError:
        return 127, "command not found"
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout:.0f}s"
    return result.returncode, (result.stdout or result.stderr).strip()


def check_git() -> Check:
    path = shutil.which("git")
    return Check(
        "git",
        ok=path is not None,
        detail=path or "not on PATH",
        remedy="Install Git and reopen the shell.",
    )


def check_docker() -> Check:
    path = shutil.which("docker")
    if path is None:
        return Check(
            "docker",
            ok=False,
            detail="not on PATH",
            remedy=(
                "Install Docker Desktop or the Docker Engine. On Windows, enable "
                "the WSL integration for this distribution in Docker Desktop."
            ),
        )
    code, output = _run(["docker", "--version"])
    if code == 0:
        return Check("docker", ok=True, detail=_one_line(output))
    # A `docker` that exists but will not answer is the WSL shim, which is
    # installed for every distribution and only works once Docker Desktop
    # turns integration on for this one.  Telling that person to reinstall
    # Docker sends them the wrong way entirely.
    return Check(
        "docker",
        ok=False,
        detail=_one_line(output) or f"`docker --version` exited {code}",
        remedy=(
            "`docker` is on PATH but does not answer. On Windows, open Docker Desktop >\n"
            "      Settings > Resources > WSL integration and enable this distribution.\n"
            "      Otherwise install the Docker Engine."
        ),
    )


def check_compose() -> Check:
    code, output = _run(["docker", "compose", "version"])
    return Check(
        "docker compose v2",
        ok=code == 0,
        detail=_one_line(output),
        remedy=(
            "Joust needs Compose v2 (`docker compose`, not `docker-compose`). "
            "Update Docker Desktop, or install the compose plugin."
        ),
    )


def check_daemon() -> Check:
    code, output = _run(["docker", "info", "--format", "{{.ServerVersion}}"], timeout=40.0)
    return Check(
        "docker daemon",
        ok=code == 0,
        detail=_one_line(output) or "no response",
        remedy="Start Docker Desktop (or `sudo systemctl start docker`) and run this again.",
    )


def _holds_posix_modes(directory: Path) -> bool:
    """Ask the filesystem, rather than guessing from the path.

    A checkout on a Windows drive mounted under WSL reports 0777 whatever
    chmod is asked for, and the token would be readable by every account on
    the machine.
    """

    try:
        with tempfile.NamedTemporaryFile(dir=directory, delete=False) as handle:
            probe = Path(handle.name)
    except OSError:
        return False
    try:
        probe.chmod(0o600)
        return stat.S_IMODE(probe.stat().st_mode) == 0o600
    except OSError:
        return False
    finally:
        probe.unlink(missing_ok=True)


def check_credential(root: Path, environment: dict[str, str]) -> Check:
    configured = environment.get("PLOW_CREDENTIALS_PATH", "").strip()
    path = Path(configured).expanduser() if configured else root / "plow-credentials"
    mint = (
        "Mint one with the official helper:\n"
        "      git clone https://github.com/plow-pbc/plow-agents.git\n"
        '      export PATH="$PWD/plow-agents/bin:$PATH"\n'
        "      plow-agents login && plow-agents lines && plow-agents mint <free-line-id>"
    )
    if not path.exists():
        return Check(
            "plow credential",
            ok=False,
            detail=f"{path} does not exist",
            remedy=mint,
            facts={"path": str(path)},
        )
    if os.name == "nt":
        return Check("plow credential", ok=True, detail=f"{path} (Windows ACLs)")
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode in CREDENTIAL_MODES:
        return Check(
            "plow credential", ok=True, detail=f"{path} mode {oct(mode)}", facts={"mode": oct(mode)}
        )
    holds_modes = _holds_posix_modes(path.parent)
    remedy = (
        f"chmod 600 {path}"
        if holds_modes
        else (
            f"{path.parent} cannot hold POSIX modes, so the token stays readable by every\n"
            "      account on this machine. Move it to the Linux filesystem and point at it:\n"
            "      mkdir -p ~/.plow && mv plow-credentials ~/.plow/credentials\n"
            "      chmod 600 ~/.plow/credentials\n"
            '      export PLOW_CREDENTIALS_PATH="$HOME/.plow/credentials"'
        )
    )
    return Check(
        "plow credential",
        ok=False,
        detail=f"{path} mode {oct(mode)} is readable by others",
        remedy=remedy,
        facts={"mode": oct(mode), "filesystem_holds_posix_modes": holds_modes},
    )


def check_agent_id(environment: dict[str, str]) -> Check:
    value = environment.get("AGENT_ID", "").strip()
    return Check(
        "AGENT_ID",
        ok=bool(value),
        detail=value or "unset",
        remedy=(
            "Choose one stable id and keep it forever; it identifies you on the Agent\n"
            "      Index and must not change across restarts:\n"
            '      export AGENT_ID="your-agent-id"'
        ),
    )


def check_disk(root: Path) -> Check:
    usage = shutil.disk_usage(root)
    gigabytes = usage.free / 1024**3
    return Check(
        "disk space",
        ok=usage.free >= REQUIRED_FREE_BYTES,
        blocking=False,
        detail=f"{gigabytes:.1f} GB free",
        remedy="The image build needs roughly 6 GB. Free some space first.",
        facts={"free_bytes": usage.free},
    )


def run_checks(root: Path, environment: dict[str, str] | None = None) -> list[Check]:
    environment = dict(os.environ if environment is None else environment)
    checks = [check_git(), check_docker()]
    if checks[-1].ok:
        checks.append(check_compose())
        checks.append(check_daemon())
    checks.append(check_credential(root, environment))
    checks.append(check_agent_id(environment))
    checks.append(check_disk(root))
    return checks


def render(checks: list[Check]) -> str:
    lines = []
    for check in checks:
        if check.ok:
            mark = "ok  "
        else:
            mark = "FAIL" if check.blocking else "warn"
        lines.append(f"  [{mark}] {check.name}: {check.detail}")
        if not check.ok and check.remedy:
            lines.append(f"      {check.remedy}")
    blocking = [check for check in checks if not check.ok and check.blocking]
    lines.append("")
    if blocking:
        names = ", ".join(check.name for check in blocking)
        lines.append(f"Not ready: {names}. Fix the above, then run this again.")
    else:
        lines.append("Ready. Start Joust with:  AGENT_ID=$AGENT_ID docker compose up --build -d")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check this machine before starting Joust.")
    parser.add_argument("--json", action="store_true", help="print the checks as JSON")
    parser.add_argument("--root", default=".", help="the Joust checkout to inspect")
    arguments = parser.parse_args(argv)

    root = Path(arguments.root).resolve()
    checks = run_checks(root)
    ready = not any(not check.ok and check.blocking for check in checks)
    if arguments.json:
        print(
            json.dumps(
                {
                    "ready": ready,
                    "checks": [
                        {
                            "name": check.name,
                            "ok": check.ok,
                            "blocking": check.blocking,
                            "detail": check.detail,
                            "remedy": check.remedy,
                            **({"facts": check.facts} if check.facts else {}),
                        }
                        for check in checks
                    ],
                },
                indent=2,
            )
        )
    else:
        print(render(checks))
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
