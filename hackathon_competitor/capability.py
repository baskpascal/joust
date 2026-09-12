from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol

from .models import CapabilityResult, Mission, Task


class Capability(Protocol):
    """A replaceable unit of mission work with a stable structured result."""

    name: str

    def execute(
        self,
        mission: Mission,
        task: Task,
        context: dict[str, Any],
    ) -> CapabilityResult: ...


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
