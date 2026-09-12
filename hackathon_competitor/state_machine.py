from __future__ import annotations

from .models import MissionState


class InvalidTransition(ValueError):
    pass


_CANONICAL = [
    MissionState.CREATED,
    MissionState.INTAKE,
    MissionState.DISCOVERY,
    MissionState.RULES_LOCK,
    MissionState.LANDSCAPE_ANALYSIS,
    MissionState.IDEATION,
    MissionState.STRATEGY_SELECTION,
    MissionState.PLANNING,
    MissionState.BUILDING,
    MissionState.VALIDATING,
    MissionState.OPTIMIZING,
    MissionState.SUBMISSION_PREP,
    MissionState.READY_FOR_SUBMISSION,
    MissionState.SUBMITTED,
    MissionState.POSTMORTEM,
]

_SIDE = {
    MissionState.PAUSED,
    MissionState.BLOCKED,
    MissionState.FAILED,
    MissionState.CANCELLED,
}


def can_transition(current: MissionState, target: MissionState) -> bool:
    if current == target:
        return True
    if target in _SIDE:
        return current not in {MissionState.CANCELLED, MissionState.POSTMORTEM}
    if current in {MissionState.PAUSED, MissionState.BLOCKED, MissionState.FAILED}:
        return target in _CANONICAL
    if current in _CANONICAL:
        index = _CANONICAL.index(current)
        return index + 1 < len(_CANONICAL) and _CANONICAL[index + 1] == target
    return False


def require_transition(current: MissionState, target: MissionState) -> None:
    if not can_transition(current, target):
        raise InvalidTransition(f"illegal mission transition: {current} -> {target}")
