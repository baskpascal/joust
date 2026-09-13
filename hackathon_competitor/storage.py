from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import TypeVar
from uuid import UUID

from pydantic import BaseModel

from .models import (
    ActionExecution,
    AgentIdentity,
    Approval,
    Artifact,
    BuildRun,
    ChangeSet,
    CompetitionCycle,
    CompetitionMemory,
    CompetitionObservation,
    CompetitionRule,
    Decision,
    EntrantProfile,
    Evaluation,
    Evidence,
    Experiment,
    HackathonSpec,
    Idea,
    Mission,
    MissionState,
    MonitorBackoffState,
    ProjectTarget,
    RepositorySnapshot,
    SourceRecord,
    Task,
    utcnow,
)

ModelT = TypeVar("ModelT", bound=BaseModel)

MIGRATIONS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS missions (
        id TEXT PRIMARY KEY,
        state TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        payload TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY,
        mission_id TEXT NOT NULL,
        status TEXT NOT NULL,
        priority INTEGER NOT NULL,
        payload TEXT NOT NULL,
        FOREIGN KEY (mission_id) REFERENCES missions(id)
    );
    CREATE INDEX IF NOT EXISTS idx_tasks_ready
      ON tasks(mission_id, status, priority DESC);
    CREATE TABLE IF NOT EXISTS task_dependencies (
        task_id TEXT NOT NULL,
        dependency_id TEXT NOT NULL,
        PRIMARY KEY (task_id, dependency_id),
        FOREIGN KEY (task_id) REFERENCES tasks(id),
        FOREIGN KEY (dependency_id) REFERENCES tasks(id)
    );
    CREATE TABLE IF NOT EXISTS specs (
        id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, payload TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS evidence (
        id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, authority TEXT NOT NULL,
        payload TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS decisions (
        id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, payload TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS artifacts (
        id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, kind TEXT NOT NULL,
        stale INTEGER NOT NULL DEFAULT 0, payload TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS evaluations (
        id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, evaluator_role TEXT NOT NULL,
        payload TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS ideas (
        id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, payload TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS events (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        mission_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        payload TEXT NOT NULL,
        occurred_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_events_mission
      ON events(mission_id, sequence);
    """,
    """
    CREATE TABLE IF NOT EXISTS experiments (
        id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, payload TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS approvals (
        id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, status TEXT NOT NULL,
        level TEXT NOT NULL, payload TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS artifact_dependencies (
        parent_artifact_id TEXT NOT NULL,
        child_artifact_id TEXT NOT NULL,
        dependency_type TEXT NOT NULL,
        PRIMARY KEY (parent_artifact_id, child_artifact_id, dependency_type),
        FOREIGN KEY (parent_artifact_id) REFERENCES artifacts(id),
        FOREIGN KEY (child_artifact_id) REFERENCES artifacts(id)
    );
    CREATE TABLE IF NOT EXISTS telemetry (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        mission_id TEXT NOT NULL,
        metric TEXT NOT NULL,
        value REAL NOT NULL,
        recorded_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS sources (
        id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, authority TEXT NOT NULL,
        uri TEXT NOT NULL, payload TEXT NOT NULL,
        UNIQUE(mission_id, uri)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS competition_memory (
        id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, category TEXT NOT NULL,
        payload TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_competition_memory_category
      ON competition_memory(category);
    """,
    """
    CREATE TABLE IF NOT EXISTS project_targets (
        id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, mode TEXT NOT NULL,
        payload TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_project_targets_mission
      ON project_targets(mission_id);
    CREATE TABLE IF NOT EXISTS repository_snapshots (
        id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, project_target_id TEXT NOT NULL,
        payload TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS build_runs (
        id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, project_target_id TEXT NOT NULL,
        payload TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS change_sets (
        id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, project_target_id TEXT NOT NULL,
        status TEXT NOT NULL, payload TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS entrant_profiles (
        id TEXT PRIMARY KEY, payload TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS competition_rules (
        id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, status TEXT NOT NULL,
        observed_at TEXT NOT NULL, payload TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_competition_rules_mission
      ON competition_rules(mission_id, observed_at);
    """,
    """
    CREATE TABLE IF NOT EXISTS competition_cycles (
        id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, sequence INTEGER NOT NULL,
        stage TEXT NOT NULL, payload TEXT NOT NULL,
        UNIQUE(mission_id, sequence)
    );
    CREATE INDEX IF NOT EXISTS idx_competition_cycles_mission
      ON competition_cycles(mission_id, sequence);
    """,
    """
    CREATE TABLE IF NOT EXISTS competition_observations (
        id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, cycle_id TEXT NOT NULL,
        observed_at TEXT NOT NULL, payload TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_competition_observations_mission
      ON competition_observations(mission_id, observed_at);
    CREATE INDEX IF NOT EXISTS idx_competition_observations_cycle
      ON competition_observations(cycle_id);
    """,
    """
    CREATE TABLE IF NOT EXISTS action_executions (
        id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, cycle_id TEXT NOT NULL,
        status TEXT NOT NULL, started_at TEXT NOT NULL, payload TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_action_executions_mission
      ON action_executions(mission_id, started_at);
    CREATE INDEX IF NOT EXISTS idx_action_executions_cycle
      ON action_executions(cycle_id);
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_identity (
        singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
        agent_id TEXT NOT NULL UNIQUE,
        payload TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS observation_fingerprints (
        fingerprint TEXT PRIMARY KEY,
        mission_id TEXT NOT NULL,
        monitor_type TEXT NOT NULL,
        observation_id TEXT,
        first_seen_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_observation_fingerprints_mission
      ON observation_fingerprints(mission_id, monitor_type, first_seen_at);
    CREATE TABLE IF NOT EXISTS monitor_leases (
        lease_key TEXT PRIMARY KEY,
        mission_id TEXT NOT NULL,
        holder TEXT NOT NULL,
        acquired_at TEXT NOT NULL,
        expires_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS monitor_backoff (
        mission_id TEXT NOT NULL,
        monitor_type TEXT NOT NULL,
        payload TEXT NOT NULL,
        PRIMARY KEY(mission_id, monitor_type)
    );
    """,
)


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def migrate(self) -> int:
        with self.connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            applied = {
                row[0] for row in connection.execute("SELECT version FROM schema_migrations")
            }
            for version, sql in enumerate(MIGRATIONS, start=1):
                if version not in applied:
                    connection.executescript(sql)
                    connection.execute(
                        "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                        (version, utcnow().isoformat()),
                    )
        return len(MIGRATIONS)

    def migration_version(self) -> int:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
            ).fetchone()
            return int(row[0])

    def bind_agent_identity(self, identity: AgentIdentity) -> AgentIdentity:
        """Bind the external id once and reject later attempts to replace it."""

        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT payload FROM agent_identity WHERE singleton = 1"
            ).fetchone()
            if row is not None:
                bound = AgentIdentity.model_validate_json(row[0])
                if bound.agent_id != identity.agent_id:
                    raise ValueError(
                        "AGENT_ID is immutable after binding: "
                        f"expected {bound.agent_id!r}, got {identity.agent_id!r}"
                    )
                return bound
            connection.execute(
                "INSERT INTO agent_identity(singleton, agent_id, payload) VALUES (1, ?, ?)",
                (identity.agent_id, self._payload(identity)),
            )
        return identity

    def get_agent_identity(self) -> AgentIdentity | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload FROM agent_identity WHERE singleton = 1"
            ).fetchone()
        return AgentIdentity.model_validate_json(row[0]) if row is not None else None

    def reserve_observation_fingerprint(
        self,
        *,
        fingerprint: str,
        mission_id: UUID | str,
        monitor_type: str,
        observation_id: UUID | str | None,
        first_seen_at: datetime,
    ) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO observation_fingerprints"
                "(fingerprint, mission_id, monitor_type, observation_id, first_seen_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    fingerprint,
                    str(mission_id),
                    monitor_type,
                    str(observation_id) if observation_id else None,
                    first_seen_at.isoformat(),
                ),
            )
            return cursor.rowcount == 1

    def has_observation_fingerprint(self, fingerprint: str) -> bool:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM observation_fingerprints WHERE fingerprint = ?",
                (fingerprint,),
            ).fetchone()
        return row is not None

    def acquire_monitor_lease(
        self,
        *,
        lease_key: str,
        mission_id: UUID | str,
        holder: str,
        acquired_at: datetime,
        expires_at: datetime,
    ) -> bool:
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT holder, expires_at FROM monitor_leases WHERE lease_key = ?",
                (lease_key,),
            ).fetchone()
            available = (
                row is None
                or row["holder"] == holder
                or datetime.fromisoformat(row["expires_at"]) <= acquired_at
            )
            if not available:
                return False
            connection.execute(
                "INSERT INTO monitor_leases"
                "(lease_key, mission_id, holder, acquired_at, expires_at) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(lease_key) DO UPDATE SET mission_id=excluded.mission_id, "
                "holder=excluded.holder, acquired_at=excluded.acquired_at, "
                "expires_at=excluded.expires_at",
                (
                    lease_key,
                    str(mission_id),
                    holder,
                    acquired_at.isoformat(),
                    expires_at.isoformat(),
                ),
            )
            return True

    def release_monitor_lease(self, *, lease_key: str, holder: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM monitor_leases WHERE lease_key = ? AND holder = ?",
                (lease_key, holder),
            )
            return cursor.rowcount == 1

    def get_monitor_backoff(self, mission_id: UUID | str, monitor_type: str) -> MonitorBackoffState:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload FROM monitor_backoff WHERE mission_id = ? AND monitor_type = ?",
                (str(mission_id), monitor_type),
            ).fetchone()
        if row is None:
            return MonitorBackoffState(mission_id=mission_id, monitor_type=monitor_type)
        return MonitorBackoffState.model_validate_json(row[0])

    def save_monitor_backoff(self, state: MonitorBackoffState) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO monitor_backoff(mission_id, monitor_type, payload) VALUES (?, ?, ?) "
                "ON CONFLICT(mission_id, monitor_type) DO UPDATE SET payload=excluded.payload",
                (str(state.mission_id), state.monitor_type, self._payload(state)),
            )

    @staticmethod
    def _payload(model: BaseModel) -> str:
        return model.model_dump_json()

    def save_mission(self, mission: Mission) -> None:
        mission.updated_at = utcnow()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO missions(id, state, updated_at, payload) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET state=excluded.state, "
                "updated_at=excluded.updated_at, payload=excluded.payload",
                (
                    str(mission.id),
                    mission.state.value,
                    mission.updated_at.isoformat(),
                    self._payload(mission),
                ),
            )

    def get_mission(self, mission_id: UUID | str) -> Mission:
        return self._get("missions", mission_id, Mission)

    def list_missions(self) -> list[Mission]:
        return self._list("missions", Mission, "updated_at DESC")

    def save_task(self, task: Task) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO tasks(id, mission_id, status, priority, payload) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET status=excluded.status, "
                "priority=excluded.priority, payload=excluded.payload",
                (
                    str(task.id),
                    str(task.mission_id),
                    task.status.value,
                    task.priority,
                    self._payload(task),
                ),
            )
            connection.execute("DELETE FROM task_dependencies WHERE task_id = ?", (str(task.id),))
            connection.executemany(
                "INSERT INTO task_dependencies(task_id, dependency_id) VALUES (?, ?)",
                [(str(task.id), str(dependency)) for dependency in task.dependencies],
            )

    def get_task(self, task_id: UUID | str) -> Task:
        return self._get("tasks", task_id, Task)

    def list_tasks(self, mission_id: UUID | str) -> list[Task]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM tasks WHERE mission_id = ? ORDER BY priority DESC, rowid",
                (str(mission_id),),
            ).fetchall()
        return [Task.model_validate_json(row[0]) for row in rows]

    def save_spec(self, spec: HackathonSpec) -> None:
        self._save("specs", spec, mission_id=spec.mission_id)

    def get_spec(self, spec_id: UUID | str) -> HackathonSpec:
        return self._get("specs", spec_id, HackathonSpec)

    def get_spec_for_mission(self, mission_id: UUID | str) -> HackathonSpec:
        items = self._list_for_mission("specs", mission_id, HackathonSpec)
        if not items:
            raise KeyError(f"no hackathon spec for mission: {mission_id}")
        return max(items, key=lambda item: item.version)

    def save_evidence(self, evidence: Evidence) -> None:
        self._save(
            "evidence", evidence, mission_id=evidence.mission_id, authority=evidence.authority
        )

    def save_source(self, source: SourceRecord) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO sources(id, mission_id, authority, uri, payload) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(mission_id, uri) DO UPDATE SET id=excluded.id, authority=excluded.authority, "
                "payload=excluded.payload",
                (
                    str(source.id),
                    str(source.mission_id),
                    source.authority,
                    source.uri,
                    self._payload(source),
                ),
            )

    def list_sources(self, mission_id: UUID | str) -> list[SourceRecord]:
        return self._list_for_mission("sources", mission_id, SourceRecord)

    def set_source_status(
        self, mission_id: UUID | str, uri: str, status: str
    ) -> SourceRecord | None:
        source = next((item for item in self.list_sources(mission_id) if item.uri == uri), None)
        if source is None:
            return None
        source.status = status
        source.retrieved_at = utcnow()
        self.save_source(source)
        return source

    def list_evidence(self, mission_id: UUID | str) -> list[Evidence]:
        return self._list_for_mission("evidence", mission_id, Evidence)

    def save_decision(self, decision: Decision) -> None:
        self._save("decisions", decision, mission_id=decision.mission_id)

    def list_decisions(self, mission_id: UUID | str) -> list[Decision]:
        return self._list_for_mission("decisions", mission_id, Decision)

    def save_artifact(self, artifact: Artifact) -> None:
        self._save(
            "artifacts",
            artifact,
            mission_id=artifact.mission_id,
            kind=artifact.kind,
            stale=int(artifact.stale),
        )

    def get_artifact(self, artifact_id: UUID | str) -> Artifact:
        return self._get("artifacts", artifact_id, Artifact)

    def list_artifacts(self, mission_id: UUID | str) -> list[Artifact]:
        return self._list_for_mission("artifacts", mission_id, Artifact)

    def save_evaluation(self, evaluation: Evaluation) -> None:
        self._save(
            "evaluations",
            evaluation,
            mission_id=evaluation.mission_id,
            evaluator_role=evaluation.evaluator_role,
        )

    def list_evaluations(self, mission_id: UUID | str) -> list[Evaluation]:
        return self._list_for_mission("evaluations", mission_id, Evaluation)

    def save_idea(self, mission_id: UUID, idea: Idea) -> None:
        self._save("ideas", idea, mission_id=mission_id)

    def list_ideas(self, mission_id: UUID | str) -> list[Idea]:
        return self._list_for_mission("ideas", mission_id, Idea)

    def save_experiment(self, experiment: Experiment) -> None:
        self._save("experiments", experiment, mission_id=experiment.mission_id)

    def list_experiments(self, mission_id: UUID | str) -> list[Experiment]:
        return self._list_for_mission("experiments", mission_id, Experiment)

    def save_competition_memory(self, memory: CompetitionMemory) -> None:
        self._save(
            "competition_memory",
            memory,
            mission_id=memory.mission_id,
            category=memory.category,
        )

    def save_entrant_profile(self, profile: EntrantProfile) -> None:
        self._save("entrant_profiles", profile)

    def get_entrant_profile(self, profile_id: UUID | str) -> EntrantProfile:
        return self._get("entrant_profiles", profile_id, EntrantProfile)

    def list_entrant_profiles(self) -> list[EntrantProfile]:
        return self._list("entrant_profiles", EntrantProfile)

    def attach_entrant_profile(self, mission_id: UUID | str, profile_id: UUID | str) -> Mission:
        mission = self.get_mission(mission_id)
        profile = self.get_entrant_profile(profile_id)
        mission.entrant_profile_id = profile.id
        self.save_mission(mission)
        return mission

    def save_competition_rule(self, rule: CompetitionRule) -> None:
        self._save(
            "competition_rules",
            rule,
            mission_id=rule.mission_id,
            status=rule.status.value,
            observed_at=rule.observed_at.isoformat(),
        )

    def list_competition_rules(self, mission_id: UUID | str) -> list[CompetitionRule]:
        return self._list_for_mission("competition_rules", mission_id, CompetitionRule)

    def save_competition_cycle(self, cycle: CompetitionCycle) -> None:
        self._save(
            "competition_cycles",
            cycle,
            mission_id=cycle.mission_id,
            sequence=cycle.sequence,
            stage=cycle.stage.value,
        )

    def get_competition_cycle(self, cycle_id: UUID | str) -> CompetitionCycle:
        return self._get("competition_cycles", cycle_id, CompetitionCycle)

    def list_competition_cycles(self, mission_id: UUID | str) -> list[CompetitionCycle]:
        return self._list_for_mission("competition_cycles", mission_id, CompetitionCycle)

    def save_competition_observation(self, observation: CompetitionObservation) -> None:
        self._save(
            "competition_observations",
            observation,
            mission_id=observation.mission_id,
            cycle_id=observation.cycle_id,
            observed_at=observation.observed_at.isoformat(),
        )

    def list_competition_observations(self, mission_id: UUID | str) -> list[CompetitionObservation]:
        return self._list_for_mission(
            "competition_observations", mission_id, CompetitionObservation
        )

    def save_action_execution(self, execution: ActionExecution) -> None:
        self._save(
            "action_executions",
            execution,
            mission_id=execution.mission_id,
            cycle_id=execution.cycle_id,
            status=execution.status.value,
            started_at=execution.started_at.isoformat(),
        )

    def list_action_executions(self, mission_id: UUID | str) -> list[ActionExecution]:
        return self._list_for_mission("action_executions", mission_id, ActionExecution)

    def save_project_target(self, target: ProjectTarget) -> None:
        self._save(
            "project_targets",
            target,
            mission_id=target.mission_id,
            mode=target.mode.value,
        )

    def attach_project_target(self, mission_id: UUID | str, target_id: UUID | str) -> Mission:
        mission = self.get_mission(mission_id)
        target = self.get_project_target(target_id)
        if target.mission_id != mission.id:
            raise ValueError("project target belongs to a different mission")
        mission.project_target_id = target.id
        self.save_mission(mission)
        return mission

    def get_project_target(self, target_id: UUID | str) -> ProjectTarget:
        return self._get("project_targets", target_id, ProjectTarget)

    def get_project_target_for_mission(self, mission_id: UUID | str) -> ProjectTarget:
        items = self._list_for_mission("project_targets", mission_id, ProjectTarget)
        if not items:
            raise KeyError(f"no project target for mission: {mission_id}")
        return items[-1]

    def list_project_targets(self, mission_id: UUID | str) -> list[ProjectTarget]:
        return self._list_for_mission("project_targets", mission_id, ProjectTarget)

    def save_repository_snapshot(self, snapshot: RepositorySnapshot) -> None:
        self._save(
            "repository_snapshots",
            snapshot,
            mission_id=snapshot.mission_id,
            project_target_id=snapshot.project_target_id,
        )

    def list_repository_snapshots(self, mission_id: UUID | str) -> list[RepositorySnapshot]:
        return self._list_for_mission("repository_snapshots", mission_id, RepositorySnapshot)

    def save_build_run(self, run: BuildRun) -> None:
        self._save(
            "build_runs",
            run,
            mission_id=run.mission_id,
            project_target_id=run.project_target_id,
        )

    def list_build_runs(self, mission_id: UUID | str) -> list[BuildRun]:
        return self._list_for_mission("build_runs", mission_id, BuildRun)

    def save_change_set(self, change_set: ChangeSet) -> None:
        self._save(
            "change_sets",
            change_set,
            mission_id=change_set.mission_id,
            project_target_id=change_set.project_target_id,
            status=change_set.status,
        )

    def list_change_sets(self, mission_id: UUID | str) -> list[ChangeSet]:
        return self._list_for_mission("change_sets", mission_id, ChangeSet)

    def list_competition_memory(self, *, category: str | None = None) -> list[CompetitionMemory]:
        if category is None:
            return self._list("competition_memory", CompetitionMemory, "rowid")
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM competition_memory WHERE category = ? ORDER BY rowid",
                (category,),
            ).fetchall()
        return [CompetitionMemory.model_validate_json(row[0]) for row in rows]

    def save_approval(self, approval: Approval) -> None:
        self._save(
            "approvals",
            approval,
            mission_id=approval.mission_id,
            status=approval.status.value,
            level=approval.level.value,
        )

    def get_approval(self, approval_id: UUID | str) -> Approval:
        return self._get("approvals", approval_id, Approval)

    def list_approvals(self, mission_id: UUID | str) -> list[Approval]:
        return self._list_for_mission("approvals", mission_id, Approval)

    def add_artifact_dependency(
        self, parent_id: UUID, child_id: UUID, dependency_type: str
    ) -> None:
        allowed = {
            "derives_from",
            "validates",
            "implements",
            "demonstrates",
            "claims",
            "supersedes",
        }
        if dependency_type not in allowed:
            raise ValueError(f"unsupported artifact dependency type: {dependency_type}")
        if parent_id == child_id:
            raise ValueError("an artifact cannot depend on itself")
        with self.connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO artifact_dependencies"
                "(parent_artifact_id, child_artifact_id, dependency_type) VALUES (?, ?, ?)",
                (str(parent_id), str(child_id), dependency_type),
            )

    def artifact_descendants(self, parent_id: UUID | str) -> list[Artifact]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                WITH RECURSIVE descendants(id) AS (
                    SELECT child_artifact_id FROM artifact_dependencies
                    WHERE parent_artifact_id = ?
                    UNION
                    SELECT dependency.child_artifact_id
                    FROM artifact_dependencies dependency
                    JOIN descendants ON dependency.parent_artifact_id = descendants.id
                )
                SELECT artifacts.payload FROM artifacts
                JOIN descendants ON artifacts.id = descendants.id
                """,
                (str(parent_id),),
            ).fetchall()
        return [Artifact.model_validate_json(row[0]) for row in rows]

    def mark_artifact_descendants_stale(self, parent_id: UUID | str) -> list[Artifact]:
        descendants = self.artifact_descendants(parent_id)
        for artifact in descendants:
            if not artifact.stale:
                artifact.stale = True
                artifact.status = "needs_review"
                self.save_artifact(artifact)
                self.append_event(
                    artifact.mission_id,
                    "ARTIFACT_STALE",
                    {"artifact_id": str(artifact.id), "upstream_artifact_id": str(parent_id)},
                )
        return descendants

    def record_metric(self, mission_id: UUID | str, metric: str, value: float) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO telemetry(mission_id, metric, value, recorded_at) VALUES (?, ?, ?, ?)",
                (str(mission_id), metric, value, utcnow().isoformat()),
            )

    def metrics(self, mission_id: UUID | str) -> list[dict[str, object]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT metric, value, recorded_at FROM telemetry WHERE mission_id = ? ORDER BY sequence",
                (str(mission_id),),
            ).fetchall()
        return [dict(row) for row in rows]

    def append_event(self, mission_id: UUID | str, event_type: str, payload: dict) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO events(mission_id, event_type, payload, occurred_at) "
                "VALUES (?, ?, ?, ?)",
                (
                    str(mission_id),
                    event_type,
                    json.dumps(payload, sort_keys=True),
                    utcnow().isoformat(),
                ),
            )
            return int(cursor.lastrowid)

    def events(self, mission_id: UUID | str) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT sequence, event_type, payload, occurred_at FROM events "
                "WHERE mission_id = ? ORDER BY sequence",
                (str(mission_id),),
            ).fetchall()
        return [
            {
                "sequence": row["sequence"],
                "event_type": row["event_type"],
                "payload": json.loads(row["payload"]),
                "occurred_at": row["occurred_at"],
            }
            for row in rows
        ]

    def export_mission(self, mission_id: UUID | str) -> dict:
        mission = self.get_mission(mission_id)
        return {
            "mission": mission.model_dump(mode="json"),
            "tasks": [item.model_dump(mode="json") for item in self.list_tasks(mission.id)],
            "evidence": [item.model_dump(mode="json") for item in self.list_evidence(mission.id)],
            "sources": [item.model_dump(mode="json") for item in self.list_sources(mission.id)],
            "decisions": [item.model_dump(mode="json") for item in self.list_decisions(mission.id)],
            "artifacts": [item.model_dump(mode="json") for item in self.list_artifacts(mission.id)],
            "evaluations": [
                item.model_dump(mode="json") for item in self.list_evaluations(mission.id)
            ],
            "ideas": [item.model_dump(mode="json") for item in self.list_ideas(mission.id)],
            "experiments": [
                item.model_dump(mode="json") for item in self.list_experiments(mission.id)
            ],
            "approvals": [item.model_dump(mode="json") for item in self.list_approvals(mission.id)],
            "competition_memory": [
                item.model_dump(mode="json")
                for item in self.list_competition_memory()
                if item.mission_id == mission.id
            ],
            "entrant_profile": (
                self.get_entrant_profile(mission.entrant_profile_id).model_dump(mode="json")
                if mission.entrant_profile_id
                else None
            ),
            "competition_rules": [
                item.model_dump(mode="json") for item in self.list_competition_rules(mission.id)
            ],
            "competition_cycles": [
                item.model_dump(mode="json") for item in self.list_competition_cycles(mission.id)
            ],
            "competition_observations": [
                item.model_dump(mode="json")
                for item in self.list_competition_observations(mission.id)
            ],
            "action_executions": [
                item.model_dump(mode="json") for item in self.list_action_executions(mission.id)
            ],
            "project_targets": [
                item.model_dump(mode="json") for item in self.list_project_targets(mission.id)
            ],
            "repository_snapshots": [
                item.model_dump(mode="json") for item in self.list_repository_snapshots(mission.id)
            ],
            "build_runs": [
                item.model_dump(mode="json") for item in self.list_build_runs(mission.id)
            ],
            "change_sets": [
                item.model_dump(mode="json") for item in self.list_change_sets(mission.id)
            ],
            "telemetry": self.metrics(mission.id),
            "events": self.events(mission.id),
        }

    def _save(self, table: str, model: BaseModel, **columns: object) -> None:
        names = ["id", *columns, "payload"]
        values = [
            str(model.id),
            *[str(value) for value in columns.values()],
            self._payload(model),
        ]
        placeholders = ", ".join("?" for _ in names)
        updates = ", ".join(f"{name}=excluded.{name}" for name in names[1:])
        with self.connect() as connection:
            connection.execute(
                f"INSERT INTO {table}({', '.join(names)}) VALUES ({placeholders}) "
                f"ON CONFLICT(id) DO UPDATE SET {updates}",
                values,
            )

    def _get(self, table: str, item_id: UUID | str, model: type[ModelT]) -> ModelT:
        with self.connect() as connection:
            row = connection.execute(
                f"SELECT payload FROM {table} WHERE id = ?", (str(item_id),)
            ).fetchone()
        if row is None:
            raise KeyError(f"{table} item not found: {item_id}")
        return model.model_validate_json(row[0])

    def _list(self, table: str, model: type[ModelT], order: str = "rowid") -> list[ModelT]:
        with self.connect() as connection:
            rows = connection.execute(f"SELECT payload FROM {table} ORDER BY {order}").fetchall()
        return [model.model_validate_json(row[0]) for row in rows]

    def _list_for_mission(
        self, table: str, mission_id: UUID | str, model: type[ModelT]
    ) -> list[ModelT]:
        with self.connect() as connection:
            rows = connection.execute(
                f"SELECT payload FROM {table} WHERE mission_id = ? ORDER BY rowid",
                (str(mission_id),),
            ).fetchall()
        return [model.model_validate_json(row[0]) for row in rows]


def transition_mission(database: Database, mission: Mission, target: MissionState) -> Mission:
    from .state_machine import require_transition

    previous = mission.state
    previous_updated_at = mission.updated_at
    require_transition(previous, target)
    mission.state = target
    database.save_mission(mission)
    database.append_event(mission.id, "STATE_CHANGED", {"from": previous.value, "to": target.value})
    elapsed = max(0.0, (mission.updated_at - previous_updated_at).total_seconds())
    database.record_metric(mission.id, f"phase_seconds:{previous.value}", elapsed)
    database.record_metric(mission.id, f"stage_reached:{target.value}", 1.0)
    return mission
