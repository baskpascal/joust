from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .models import CapabilityResult, Mission, Task
from .storage import Database


@dataclass(frozen=True)
class MissionContext:
    mission: Mission
    database: Database
    artifact_root: Path
    services: dict[str, Any] = field(default_factory=dict)


class Capability(Protocol):
    """A replaceable unit of mission work with a stable structured result."""

    name: str

    def can_handle(self, task: Task) -> bool: ...

    async def execute(self, task: Task, ctx: MissionContext) -> CapabilityResult: ...


class FunctionCapability:
    def __init__(
        self,
        name: str,
        handler: Callable[[Task, MissionContext], Awaitable[CapabilityResult]],
    ):
        if not name:
            raise ValueError("capability name cannot be empty")
        self.name = name
        self._handler = handler

    def can_handle(self, task: Task) -> bool:
        return task.capability == self.name

    async def execute(self, task: Task, ctx: MissionContext) -> CapabilityResult:
        if not self.can_handle(task):
            raise ValueError(f"{self.name} cannot handle task capability {task.capability}")
        return await self._handler(task, ctx)


class CapabilityRegistry:
    def __init__(self, capabilities: Iterable[Capability] = ()):
        self._capabilities: dict[str, Capability] = {}
        for capability in capabilities:
            self.register(capability)

    def register(self, capability: Capability) -> None:
        if not capability.name:
            raise ValueError("capability name cannot be empty")
        if capability.name in self._capabilities:
            raise ValueError(f"capability already registered: {capability.name}")
        self._capabilities[capability.name] = capability

    def get(self, name: str) -> Capability:
        try:
            return self._capabilities[name]
        except KeyError as exc:
            raise LookupError(f"capability is not registered: {name}") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._capabilities))

    async def dispatch(self, task: Task, ctx: MissionContext) -> CapabilityResult:
        capability = self.get(task.capability)
        if not capability.can_handle(task):
            raise LookupError(f"capability rejected task: {task.capability}")
        return await capability.execute(task, ctx)
