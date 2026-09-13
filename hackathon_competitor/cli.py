from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import UUID

from .build_loop import CommandImplementer, project_environment
from .distribution import build_public_bundle
from .exporter import export_mission_bundle
from .github import GitHubCliAdapter
from .models import MissionState, ProjectMode, ProjectTarget
from .orchestrator import MissionOrchestrator
from .pipeline import build_project_for_mission, complete_v0, mission_status, run_vertical_slice
from .registry import default_registry
from .rule_updates import refresh_official_rules
from .storage import MIGRATIONS, Database


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
    return MissionOrchestrator(
        database,
        root / "missions",
        capability_registry=default_registry(),
    )


def _runtime_marker_present(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _parse_command_vectors(values: list[str]) -> list[list[str]]:
    commands: list[list[str]] = []
    for value in values:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"command must be a JSON argv list: {value!r}") from exc
        if (
            not isinstance(parsed, list)
            or not parsed
            or any(not isinstance(argument, str) or not argument for argument in parsed)
        ):
            raise ValueError("command must be a non-empty JSON list of non-empty strings")
        commands.append(parsed)
    return commands


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

    workspace_root = root / "missions"
    try:
        workspace_root.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=workspace_root, delete=True):
            pass
        checks["workspace"] = {"ok": True, "path": str(workspace_root)}
    except OSError as exc:
        checks["workspace"] = {"ok": False, "error": str(exc)}

    database = Database(root / "state.db")
    try:
        current = database.migrate()
        checks["database"] = {"ok": current == len(MIGRATIONS), "version": current}
    except Exception as exc:  # noqa: BLE001 - doctor must report every failed check
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
    plow_tools_available = (
        bool(os.environ.get("PLOW_MCP_URL"))
        or shutil.which("plow-gog") is not None
        or _runtime_marker_present(Path("/run/s6/container_environment/PLOW_MCP_URL"))
    )
    checks["plow_tools"] = {
        "ok": plow_tools_available,
        "available": plow_tools_available,
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
    client = Path("/opt/plow/agent-index-client.py")
    if client.is_file():
        smoke_environment = os.environ.copy()
        hermes_home = Path(os.environ.get("HERMES_HOME") or root).resolve()
        smoke_environment["HOME"] = str(hermes_home)
        smoke_environment["HERMES_HOME"] = str(hermes_home)
        try:
            result = subprocess.run(
                [sys.executable, str(client), "status"],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
                env=smoke_environment,
            )
            checks["agent_index_client_smoke"] = {
                "ok": result.returncode in {0, 3},
                "available": True,
                "status": "registered" if result.returncode == 0 else "not_registered",
            }
        except (OSError, subprocess.TimeoutExpired) as exc:
            checks["agent_index_client_smoke"] = {
                "ok": False,
                "available": True,
                "error_type": type(exc).__name__,
            }
    else:
        checks["agent_index_client_smoke"] = {"ok": True, "available": False}

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
    for name in ("show", "resume", "tasks"):
        sub = mission_commands.add_parser(name)
        sub.add_argument("mission_id", type=UUID)
    export = mission_commands.add_parser("export")
    export.add_argument("mission_id", type=UUID)
    export.add_argument("--bundle", type=Path)
    refresh = mission_commands.add_parser("refresh-rules")
    refresh.add_argument("mission_id", type=UUID)
    refresh.add_argument("--url", required=True)
    attach = mission_commands.add_parser("attach-project")
    attach.add_argument("mission_id", type=UUID)
    attach.add_argument("--path", required=True)
    attach.add_argument(
        "--mode",
        choices=[mode.value for mode in ProjectMode],
        default=ProjectMode.EXISTING_REPO.value,
    )
    attach.add_argument("--repo")
    attach.add_argument("--default-branch", default="main")
    attach.add_argument(
        "--install-command", action="append", default=[], metavar="JSON_ARGV",
        help='repeatable JSON argv, e.g. ["python","-m","pip","install","-e", "."]',
    )
    attach.add_argument("--build-command", action="append", default=[], metavar="JSON_ARGV")
    attach.add_argument("--test-command", action="append", default=[], metavar="JSON_ARGV")
    attach.add_argument("--run-command", action="append", default=[], metavar="JSON_ARGV")
    attach.add_argument(
        "--environment-name",
        action="append",
        default=[],
        metavar="NAME",
        help="repeatable non-sensitive host environment name approved for project commands",
    )
    build = mission_commands.add_parser("build-project")
    build.add_argument("mission_id", type=UUID)
    build.add_argument("--implementation-command", required=True, metavar="JSON_ARGV")
    build.add_argument("--spec")
    build.add_argument("--max-repairs", type=int, default=0)

    db = commands.add_parser("db")
    db_commands = db.add_subparsers(dest="db_command", required=True)
    db_commands.add_parser("migrate")
    commands.add_parser("doctor")
    bundle = commands.add_parser("bundle")
    bundle.add_argument("--output", type=Path, default=Path("dist/galahad-public.zip"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    home = args.home
    if args.command == "doctor":
        checks, healthy = doctor(home)
        print(json.dumps({"healthy": healthy, "checks": checks}, indent=2))
        return 0 if healthy else 1
    if args.command == "bundle":
        print(json.dumps(build_public_bundle(Path.cwd(), args.output), indent=2))
        return 0
    app = runtime(home)
    if args.command == "db":
        print(json.dumps({"migration_version": app.database.migration_version()}))
        return 0
    if args.mission_command == "create":
        mission = run_vertical_slice(app, args.url, workspace_path=args.workspace)
        print(json.dumps(mission_status(app, mission), indent=2))
        return 0
    if args.mission_command == "attach-project":
        # Validate the names at attachment time so a credential-shaped name
        # cannot be persisted as a future build permission.
        project_environment(args.environment_name)
        target = ProjectTarget(
            mission_id=args.mission_id,
            mode=ProjectMode(args.mode),
            local_path=str(Path(args.path).resolve()),
            repository_url=args.repo,
            default_branch=args.default_branch,
            install_commands=_parse_command_vectors(args.install_command),
            build_commands=_parse_command_vectors(args.build_command),
            test_commands=_parse_command_vectors(args.test_command),
            run_commands=_parse_command_vectors(args.run_command),
            environment_allowlist=list(args.environment_name),
        )
        app.attach_project_target(target)
        print(json.dumps(target.model_dump(mode="json"), indent=2))
        return 0
    if args.mission_command == "build-project":
        if args.max_repairs < 0:
            raise ValueError("--max-repairs cannot be negative")
        target = app.database.get_project_target_for_mission(args.mission_id)
        implementation_command = _parse_command_vectors([args.implementation_command])[0]
        implementer = CommandImplementer(implementation_command)
        specification = args.spec
        if specification and Path(specification).is_file():
            specification = Path(specification).read_text(encoding="utf-8")
        change_set = build_project_for_mission(
            app,
            args.mission_id,
            implementer,
            specification=specification,
            max_repairs=args.max_repairs,
            github=GitHubCliAdapter(str(Path(target.local_path).resolve().parent)),
        )
        print(json.dumps(change_set.model_dump(mode="json"), indent=2))
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
        if args.bundle:
            path = export_mission_bundle(app.database, mission.id, args.bundle)
            print(json.dumps({"mission": str(mission.id), "bundle": str(path)}, indent=2))
        else:
            print(json.dumps(app.database.export_mission(mission.id), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
