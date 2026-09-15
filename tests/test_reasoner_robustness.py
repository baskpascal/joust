"""ClaudeCliReasoner must classify a CLI result, not just its exit code.

`--max-turns 1` alone reached ~40-50% failure in live use: a model spending
its one turn on a tool call (denied or not) never produces a final answer.
These tests pin the fix down to real observed CLI envelopes, captured from
`claude -p ... --output-format json`, rather than a guess at their shape.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from hackathon_competitor.ai import ClaudeCliReasoner, ModelUnavailable

SUCCESS_ENVELOPE = {
    "is_error": False,
    "subtype": "success",
    "num_turns": 1,
    "result": "OK",
    "stop_reason": "end_turn",
}

MAX_TURNS_ENVELOPE = {
    "is_error": True,
    "subtype": "error_max_turns",
    "terminal_reason": "max_turns",
    "stop_reason": "tool_use",
    "errors": ["Reached maximum number of turns (3)"],
    "num_turns": 4,
}

EMPTY_SUCCESS_ENVELOPE = {
    "is_error": False,
    "subtype": "success",
    "result": "   ",
}


class _Completed(SimpleNamespace):
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0


def _fake_run(envelopes: list[dict], calls: list[list[str]]):
    def run(argv, **kwargs):
        calls.append(argv)
        envelope = envelopes[len(calls) - 1]
        return _Completed(stdout=json.dumps(envelope), stderr="", returncode=0)

    return run


def _reasoner(
    monkeypatch, envelopes: list[dict], *, max_attempts: int = 3
) -> tuple[ClaudeCliReasoner, list[list[str]]]:
    calls: list[list[str]] = []
    monkeypatch.setattr("hackathon_competitor.ai.shutil.which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr("hackathon_competitor.ai.subprocess.run", _fake_run(envelopes, calls))
    monkeypatch.setattr("hackathon_competitor.ai.time.sleep", lambda seconds: None)
    reasoner = ClaudeCliReasoner(max_attempts=max_attempts)
    return reasoner, calls


def test_a_clean_success_returns_the_result_text_on_the_first_call(monkeypatch):
    reasoner, calls = _reasoner(monkeypatch, [SUCCESS_ENVELOPE])
    assert reasoner.complete("hello") == "OK"
    assert len(calls) == 1
    assert "--output-format" in calls[0] and "json" in calls[0]
    assert "--disallowedTools" in calls[0]


def test_a_transient_max_turns_failure_is_retried_and_then_succeeds(monkeypatch):
    reasoner, calls = _reasoner(monkeypatch, [MAX_TURNS_ENVELOPE, SUCCESS_ENVELOPE])
    assert reasoner.complete("hello") == "OK"
    assert len(calls) == 2


def test_max_turns_exhausted_after_every_retry_names_the_real_cause(monkeypatch):
    reasoner, calls = _reasoner(
        monkeypatch, [MAX_TURNS_ENVELOPE, MAX_TURNS_ENVELOPE, MAX_TURNS_ENVELOPE]
    )
    with pytest.raises(ModelUnavailable) as excinfo:
        reasoner.complete("hello")
    assert len(calls) == 3
    assert excinfo.value.code == "REASONING_PROVIDER_TURN_BUDGET_EXCEEDED"
    # Telemetry: every attempt is named, not just the last one.
    assert excinfo.value.detail.count("attempt") == 3


def test_a_non_json_envelope_is_not_retried(monkeypatch):
    calls: list[list[str]] = []

    def run(argv, **kwargs):
        calls.append(argv)
        return _Completed(stdout="not json", stderr="crashed", returncode=1)

    monkeypatch.setattr("hackathon_competitor.ai.shutil.which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr("hackathon_competitor.ai.subprocess.run", run)
    reasoner = ClaudeCliReasoner(max_attempts=3)
    with pytest.raises(ModelUnavailable) as excinfo:
        reasoner.complete("hello")
    assert excinfo.value.code == "REASONING_PROVIDER_UNAVAILABLE"
    # A crash before any structured result exists is not a classifiable
    # model failure, and retrying an unparseable process cannot help.
    assert len(calls) == 1


def test_success_with_no_answer_text_is_treated_as_an_invalid_response(monkeypatch):
    reasoner, calls = _reasoner(monkeypatch, [EMPTY_SUCCESS_ENVELOPE] * 3)
    with pytest.raises(ModelUnavailable) as excinfo:
        reasoner.complete("hello")
    assert excinfo.value.code == "REASONING_PROVIDER_INVALID_RESPONSE"
    assert len(calls) == 3


def test_a_missing_executable_never_calls_the_subprocess(monkeypatch):
    monkeypatch.setattr("hackathon_competitor.ai.shutil.which", lambda name: None)
    reasoner = ClaudeCliReasoner()
    with pytest.raises(ModelUnavailable) as excinfo:
        reasoner.complete("hello")
    assert excinfo.value.code == "REASONING_PROVIDER_UNAVAILABLE"


def test_an_unrecognised_provider_error_is_still_classified_and_retried(monkeypatch):
    other_error = {
        "is_error": True,
        "subtype": "error_during_execution",
        "errors": ["upstream request failed"],
        "stop_reason": "error",
    }
    reasoner, calls = _reasoner(monkeypatch, [other_error, SUCCESS_ENVELOPE])
    assert reasoner.complete("hello") == "OK"
    assert len(calls) == 2
