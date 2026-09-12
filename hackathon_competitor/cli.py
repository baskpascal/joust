from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path
from uuid import UUID

from .orchestrator import MissionOrchestrator
from .models import MissionState
from .pipeline import complete_v0, mission_status, run_vertical_slice
from .rule_updates import refresh_official_rules
from .storage import Database, MIGRATIONS


def default_home() -> Path:
    configured = os.environ.get("HACKATHON_COMPETITOR_HOME")
    if configured:
        return Path(configured)
    runtime_home = Path("/var/lib/hermes")
    if runtime_home.is_dir():
        return runtime_home / "hackathon_competitor"
    return Path.home() / ".galahad"


def runtime(home: Path | None = None) -> MissionOrchestrator:
    root = (home or default_home()).resolve()
    database = Database(root / "state.db")
    database.migrate()
    return MissionOrchestrator(database, root / "missions")


def doctor(home: Path | None = None) -> tuple[dict[str, dict[str, object]], bool]:
    root = (home or default_home()).resolve()
    checks: dict[str, dict[str, object]] = {}
    try:
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=root, delete=True):
            pass
        checks["state_directory"] = {"ok": True, "path": str(root)}
    except OSError as exc:
        checks["state_directory"] = {"ok": False, "error": str(exc)}

    database = Database(root / "state.db")
    try:
        current = database.migrate()
        checks["database"] = {"ok": current == len(MIGRATIONS), "version": current}
    except Exception as exc:
        checks["database"] = {"ok": False, "error": str(exc)}

    checks["git"] = {"ok": shutil.which("git") is not None}
    repo_root = Path(__file__).resolve().parents[1]
    expected_skills = [
        "hackathon-intake",
        "hackathon-research",
        "hackathon-strategy",
        "hackathon-build",
        "hackathon-red-team",
        "hackathon-submit",
    ]
    skill_roots = [repo_root / "skills", Path("/opt/hermes/skills")]
    installed = {
        name: any((skill_root / name / "SKILL.md").is_file() for skill_root in skill_roots)
        for name in expected_skills
    }
    checks["skills"] = {"ok": all(installed.values()), "installed": installed}
    checks["plow_tools"] = {
        "ok": bool(os.environ.get("PLOW_MCP_URL")) or shutil.which("plow-gog") is not None,
        "available": bool(os.environ.get("PLOW_MCP_URL")) or shutil.which("plow-gog") is not None,
    }
    checks["agent_id"] = {
        "ok": bool(os.environ.get("AGENT_ID")),
        "present": bool(os.environ.get("AGENT_ID")),
    }
    service_candidates = [
        repo_root / "image/s6-overlay/s6-rc.d/agent-index/run",
        Path("/etc/s6-overlay/s6-rc.d/agent-index/run"),
    ]
    checks["agent_index_service"] = {"ok": any(path.is_file() for path in service_candidates)}

    credential_candidates = [repo_root / "plow-credentials", Path("/var/lib/plow/credentials")]
    credential = next((path for path in credential_candidates if path.exists()), None)
    if credential is None:
        checks["credentials"] = {"ok": True, "present": False}
    else:
        mode = stat.S_IMODE(credential.stat().st_mode)
        checks["credentials"] = {
            "ok": os.name == "nt" or mode in {0o400, 0o600},
            "present": True,
            "mode": oct(mode),
        }
    healthy = all(check["ok"] for check in checks.values())
    return checks, healthy


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="galahad")
    parser.add_argument("--home", type=Path, help="state directory override")
    commands = parser.add_subparsers(dest="command", required=True)

    mission = commands.add_parser("mission")
    mission_commands = mission.add_subparsers(dest="mission_command", required=True)
    create = mission_commands.add_parser("create")
    create.add_argument("--url", required=True)
    create.add_argument("--workspace", default=".")
    for name in ("show", "resume", "tasks", "export"):
        sub = mission_commands.add_parser(name)
        sub.add_argument("mission_id", type=UUID)
    refresh = mission_commands.add_parser("refresh-rules")
    refresh.add_argument("mission_id", type=UUID)
    refresh.add_argument("--url", required=True)

    db = commands.add_parser("db")
    db_commands = db.add_subparsers(dest="db_command", required=True)
    db_commands.add_parser("migrate")
    commands.add_parser("doctor")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    home = args.home
    if args.command == "doctor":
        checks, healthy = doctor(home)
        print(json.dumps({"healthy": healthy, "checks": checks}, indent=2))
        return 0 if healthy else 1
    app = runtime(home)
    if args.command == "db":
        print(json.dumps({"migration_version": app.database.migration_version()}))
        return 0
    if args.mission_command == "create":
        mission = run_vertical_slice(app, args.url, workspace_path=args.workspace)
        print(json.dumps(mission_status(app, mission), indent=2))
        return 0
    if args.mission_command == "resume":
        resumed = app.resume_mission(args.mission_id)
        mission = (
            complete_v0(app, resumed.id) if resumed.state == MissionState.PLANNING else resumed
        )
    elif args.mission_command == "refresh-rules":
        spec = refresh_official_rules(app, args.mission_id, args.url)
        mission = app.database.get_mission(args.mission_id)
        print(
            json.dumps(
                {
                    "mission": str(mission.id),
                    "rules_version": spec.version,
                    "state": mission.state.value,
                },
                indent=2,
            )
        )
        return 0
    else:
        mission = app.database.get_mission(args.mission_id)
    if args.mission_command in {"show", "resume"}:
        print(json.dumps(mission_status(app, mission), indent=2))
    elif args.mission_command == "tasks":
        print(
            json.dumps(
                [task.model_dump(mode="json") for task in app.database.list_tasks(mission.id)],
                indent=2,
            )
        )
    elif args.mission_command == "export":
        print(json.dumps(app.database.export_mission(mission.id), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
