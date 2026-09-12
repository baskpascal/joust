import pytest

from hackathon_competitor.models import MissionState
from hackathon_competitor.state_machine import InvalidTransition, require_transition


def test_canonical_next_transition_is_legal():
    require_transition(MissionState.DISCOVERY, MissionState.RULES_LOCK)


def test_skipping_a_quality_gate_is_illegal():
    with pytest.raises(InvalidTransition):
        require_transition(MissionState.DISCOVERY, MissionState.IDEATION)


def test_terminal_cancelled_state_cannot_resume():
    with pytest.raises(InvalidTransition):
        require_transition(MissionState.CANCELLED, MissionState.DISCOVERY)
