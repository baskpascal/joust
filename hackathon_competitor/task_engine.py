from __future__ import annotations

from collections import defaultdict, deque
from datetime import timedelta
from uuid import UUID

from .models import Task, TaskStatus, utcnow
from .storage import Database


class DependencyError(ValueError):
    pass


class TaskEngine:
    def __init__(self, database: Database, *, retry_base_seconds: float = 5.0):
        self.database = database
        self.retry_base_seconds = retry_base_seconds

    def add_tasks(self, tasks: list[Task]) -> None:
        if not tasks:
            return
        mission_ids = {task.mission_id for task in tasks}
        if len(mission_ids) != 1:
            raise DependencyError("a task batch must belong to one mission")
        mission_id = tasks[0].mission_id
        existing = {task.id: task for task in self.database.list_tasks(mission_id)}
        batch = {task.id: task for task in tasks}
        if len(batch) != len(tasks):
            raise DependencyError("duplicate task id in batch")
        duplicates = set(batch).intersection(existing)
        if duplicates:
            raise DependencyError(f"task ids already exist: {duplicates}")

        known = set(existing) | set(batch)
        for task in tasks:
            missing = set(task.dependencies) - known
            if missing:
                raise DependencyError(f"task {task.id} has unknown dependencies: {missing}")
            if task.id in task.dependencies:
                raise DependencyError(f"task {task.id} depends on itself")

        graph = {item.id: list(item.dependencies) for item in [*existing.values(), *tasks]}
        self._require_acyclic(graph)

        pending = dict(batch)
        persisted = set(existing)
        while pending:
            ready = [
                task for task in pending.values() if set(task.dependencies).issubset(persisted)
            ]
            if not ready:
                raise DependencyError("task dependency graph cannot be persisted")
            for task in ready:
                self.database.save_task(task)
                self.database.append_event(
                    task.mission_id,
                    "TASK_CREATED",
                    {"task_id": str(task.id), "type": task.type},
                )
                persisted.add(task.id)
                pending.pop(task.id)

    @staticmethod
    def _require_acyclic(graph: dict[UUID, list[UUID]]) -> None:
        visiting: set[UUID] = set()
        visited: set[UUID] = set()

        def visit(node: UUID) -> None:
            if node in visiting:
                raise DependencyError("task graph contains a cycle")
            if node in visited:
                return
            visiting.add(node)
            for dependency in graph.get(node, []):
                visit(dependency)
            visiting.remove(node)
            visited.add(node)

        for node in graph:
            visit(node)

    def refresh_ready(self, mission_id: UUID) -> list[Task]:
        tasks = self.database.list_tasks(mission_id)
        statuses = {task.id: task.status for task in tasks}
        ready: list[Task] = []
        for task in tasks:
            candidate = task.status in {TaskStatus.PENDING, TaskStatus.FAILED_RETRYABLE}
            dependencies_done = all(
                statuses.get(dependency) == TaskStatus.SUCCEEDED for dependency in task.dependencies
            )
            retry_due = task.retry_after is None or task.retry_after <= utcnow()
            if (
                candidate
                and dependencies_done
                and retry_due
                and task.retry_count <= task.max_retries
            ):
                task.status = TaskStatus.READY
                task.error = None
                task.retry_after = None
                self.database.save_task(task)
                ready.append(task)
        return sorted(ready, key=lambda task: (-task.priority, task.created_at))

    def claim(self, task_id: UUID) -> Task:
        task = self.database.get_task(task_id)
        if task.status != TaskStatus.READY:
            raise DependencyError(f"task {task.id} is not ready")
        task.status = TaskStatus.RUNNING
        task.started_at = utcnow()
        task.finished_at = None
        self.database.save_task(task)
        self.database.append_event(task.mission_id, "TASK_STARTED", {"task_id": str(task.id)})
        return task

    def succeed(self, task_id: UUID) -> Task:
        task = self.database.get_task(task_id)
        if task.status != TaskStatus.RUNNING:
            raise DependencyError(f"task {task.id} is not running")
        task.status = TaskStatus.SUCCEEDED
        task.finished_at = utcnow()
        task.error = None
        task.retry_after = None
        self.database.save_task(task)
        self.database.append_event(task.mission_id, "TASK_SUCCEEDED", {"task_id": str(task.id)})
        return task

    def fail(self, task_id: UUID, error: str, retryable: bool = True) -> Task:
        task = self.database.get_task(task_id)
        if task.status != TaskStatus.RUNNING:
            raise DependencyError(f"task {task.id} is not running")
        task.retry_count += 1
        can_retry = retryable and task.retry_count <= task.max_retries
        task.status = TaskStatus.FAILED_RETRYABLE if can_retry else TaskStatus.FAILED_PERMANENT
        task.finished_at = utcnow()
        task.error = error
        task.retry_after = (
            utcnow() + timedelta(seconds=self.retry_base_seconds * (2 ** (task.retry_count - 1)))
            if can_retry
            else None
        )
        self.database.save_task(task)
        self.database.append_event(
            task.mission_id,
            "TASK_FAILED",
            {"task_id": str(task.id), "retryable": can_retry, "error": error},
        )
        return task

    def recover_running(self, mission_id: UUID) -> list[Task]:
        recovered: list[Task] = []
        for task in self.database.list_tasks(mission_id):
            if task.status == TaskStatus.RUNNING:
                task.retry_count += 1
                task.status = (
                    TaskStatus.FAILED_RETRYABLE
                    if task.retry_count <= task.max_retries
                    else TaskStatus.FAILED_PERMANENT
                )
                task.error = "worker stopped while task was running"
                task.retry_after = (
                    utcnow()
                    + timedelta(seconds=self.retry_base_seconds * (2 ** (task.retry_count - 1)))
                    if task.status == TaskStatus.FAILED_RETRYABLE
                    else None
                )
                task.finished_at = utcnow()
                self.database.save_task(task)
                self.database.append_event(
                    mission_id,
                    "TASK_FAILED",
                    {
                        "task_id": str(task.id),
                        "retryable": task.status == TaskStatus.FAILED_RETRYABLE,
                        "error": task.error,
                    },
                )
                recovered.append(task)
        return recovered

    def cancel_from(self, task_id: UUID) -> list[Task]:
        root = self.database.get_task(task_id)
        tasks = self.database.list_tasks(root.mission_id)
        children: dict[UUID, list[UUID]] = defaultdict(list)
        for task in tasks:
            for dependency in task.dependencies:
                children[dependency].append(task.id)
        queue = deque([root.id])
        cancelled: list[Task] = []
        while queue:
            current = queue.popleft()
            task = self.database.get_task(current)
            if task.status not in {TaskStatus.SUCCEEDED, TaskStatus.CANCELLED}:
                task.status = TaskStatus.CANCELLED
                task.finished_at = utcnow()
                self.database.save_task(task)
                cancelled.append(task)
            queue.extend(children[current])
        return cancelled
