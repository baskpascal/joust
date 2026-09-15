"""The boundary between Joust and a real model, and the record it leaves.

Joust's promise is that a model decides what to build. Nothing in the stored
state used to distinguish a model's decision from a hash's, so this module does
two things and no more: it reaches an actual provider, and it writes down what
that call was and what came back.

When no provider answers, the call raises rather than degrading into a
deterministic imitation. A mission that cannot reach a model is a mission that
stops with a named boundary.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from .models import (
    AIDecision,
    ModelInvocation,
    ModelInvocationStatus,
    utcnow,
)
from .storage import Database


class ModelUnavailable(RuntimeError):
    """No model answered. Carries the boundary code the mission reports."""

    def __init__(self, code: str, detail: str = ""):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


class ModelResponseInvalid(ValueError):
    """A model answered, but with no JSON object anywhere in the text.

    Kept as a `ValueError` so existing `except ValueError` handling still
    catches it, but carries its own `code` so a caller can report exactly
    why the mission stopped instead of a generic rejection — this is
    "unparseable", never confused with "parsed fine but rejected its
    content", which is what `StrategyRejected` is for.
    """

    code = "MODEL_RESPONSE_INVALID"


class Reasoner(Protocol):
    """A text-in/text-out model. Implementations must be real providers."""

    provider: str
    model: str

    def complete(self, prompt: str) -> str: ...


# A reasoning call is a self-contained text-in/text-out completion: the
# prompt already carries everything the model needs, so it has no legitimate
# reason to invoke a tool. Denying every built-in tool removes the actual
# cause of the "reached max turns" failure (the model spending its one turn
# on a tool call instead of an answer) rather than just giving it more turns
# to eventually get around to answering. This list is deliberately named
# tools, not "no tools" behaviour Joust cannot verify across CLI versions.
_NO_TOOL_REASONING_ARGS = [
    "--disallowedTools",
    "Bash Read Write Edit MultiEdit Glob Grep WebFetch WebSearch Task "
    "TodoWrite NotebookEdit BashOutput KillBash SlashCommand",
]

# Even with every tool denied, a model can still spend a turn attempting one
# and recovering from the denial before answering in text. Three turns is a
# bounded margin for exactly that (attempt, denial, answer) — not the same
# as raising the limit to make the symptom go away; the tool denial above is
# what actually addresses the cause.
_REASONING_MAX_TURNS = 3

# Turn-budget exhaustion has been observed to be transient: an identical
# prompt, replayed with no change, has succeeded on a later attempt. A
# bounded retry reflects that; it is not applied to failures a retry cannot
# fix (the binary missing, for instance).
_REASONING_MAX_ATTEMPTS = 3


class ClaudeCliReasoner:
    """The Claude Code CLI in non-interactive mode.

    Chosen because it is a coding agent that is already authenticated on the
    host where Joust's missions run; `-p` returns one final answer and exits.
    """

    def __init__(
        self,
        *,
        executable: str = "claude",
        model: str = "default",
        timeout_seconds: float = 300.0,
        workdir: str | Path | None = None,
        max_turns: int = _REASONING_MAX_TURNS,
        max_attempts: int = _REASONING_MAX_ATTEMPTS,
    ):
        self.executable = executable
        self.provider = "claude-code-cli"
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.workdir = Path(workdir).resolve() if workdir else None
        if max_turns < 1:
            raise ValueError("max_turns must be at least 1")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self.max_turns = max_turns
        self.max_attempts = max_attempts

    def _invoke(self, resolved: str, prompt: str) -> dict:
        """Run one CLI call and return its structured `--output-format json` envelope.

        Raises `ModelUnavailable` directly for failures a retry cannot help
        with (the process never producing a JSON envelope at all); returns
        the parsed envelope, error or not, for everything else so the caller
        can classify it and decide whether to retry.
        """

        argv = [
            resolved,
            "-p",
            prompt,
            "--output-format",
            "json",
            "--max-turns",
            str(self.max_turns),
            *_NO_TOOL_REASONING_ARGS,
        ]
        if self.model and self.model != "default":
            argv.extend(["--model", self.model])
        try:
            result = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
                cwd=str(self.workdir) if self.workdir else None,
                env={**os.environ, "CLAUDE_CODE_ENTRYPOINT": "joust"},
            )
        except subprocess.TimeoutExpired as error:
            raise ModelUnavailable(
                "REASONING_PROVIDER_TIMEOUT", f"no answer in {self.timeout_seconds:.0f}s"
            ) from error
        try:
            envelope = json.loads(result.stdout)
        except (json.JSONDecodeError, ValueError):
            # The process ran but never produced the structured result the
            # CLI documents for --output-format json: a crash before any
            # turn completed, not a classifiable model-level failure.
            raise ModelUnavailable(
                "REASONING_PROVIDER_UNAVAILABLE",
                (result.stderr or result.stdout).strip()[:400] or f"exit {result.returncode}",
            ) from None
        return envelope

    def _classify(self, envelope: dict) -> tuple[str, str, bool]:
        """Return (code, detail, retryable) for one CLI result envelope."""

        if not envelope.get("is_error"):
            text = str(envelope.get("result") or "").strip()
            if not text:
                return (
                    "REASONING_PROVIDER_INVALID_RESPONSE",
                    "provider reported success with no answer text",
                    True,
                )
            return "", text, False
        subtype = str(envelope.get("subtype") or "unknown")
        errors = envelope.get("errors") or []
        detail = "; ".join(str(item) for item in errors) or subtype
        if subtype == "error_max_turns":
            return (
                "REASONING_PROVIDER_TURN_BUDGET_EXCEEDED",
                f"{detail} (stop_reason={envelope.get('stop_reason')})",
                True,
            )
        # Anything else reported as an error by the provider itself
        # (permission denial, an API error, a malformed request) — retrying
        # blind is the CLI's own recommended recovery for a transient
        # provider error, so it is retried too, just without the specific
        # turn-budget classification.
        return f"REASONING_PROVIDER_ERROR_{subtype.upper()}", detail, True

    def complete(self, prompt: str) -> str:
        resolved = shutil.which(self.executable)
        if resolved is None:
            raise ModelUnavailable(
                "REASONING_PROVIDER_UNAVAILABLE", f"{self.executable} is not on PATH"
            )
        attempts: list[str] = []
        for attempt in range(1, self.max_attempts + 1):
            envelope = self._invoke(resolved, prompt)
            code, detail, retryable = self._classify(envelope)
            if not code:
                return detail
            attempts.append(f"attempt {attempt}: {code}: {detail}"[:300])
            if not retryable or attempt >= self.max_attempts:
                raise ModelUnavailable(code, " | ".join(attempts))
            time.sleep(1.5 * attempt)
        raise AssertionError("unreachable: loop always returns or raises")


class UnavailableReasoner:
    """The ablation provider: every call reports the boundary.

    It exists so that "Joust without a model" is a state the product can be
    run in and observed, rather than an argument.
    """

    provider = "none"
    model = "none"

    def __init__(
        self,
        code: str = "AI_STRATEGY_UNAVAILABLE",
        detail: str = "no reasoning provider is configured",
    ):
        self.code = code
        self.detail = detail

    def complete(self, prompt: str) -> str:
        raise ModelUnavailable(self.code, self.detail)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class InvocationRecorder:
    """Run one model call and persist what it was.

    The prompt and the context are stored as digests, not text: the record has
    to prove which inputs produced which output without copying a competition's
    pages into the state database.
    """

    def __init__(self, database: Database, mission_id: UUID):
        self.database = database
        self.mission_id = mission_id

    def run(
        self,
        reasoner: Reasoner,
        *,
        purpose: str,
        prompt: str,
        context: Any,
    ) -> tuple[str, ModelInvocation]:
        invocation = ModelInvocation(
            mission_id=self.mission_id,
            purpose=purpose,
            provider=getattr(reasoner, "provider", reasoner.__class__.__name__),
            model=getattr(reasoner, "model", "unknown"),
            input_context_hash=_hash(json.dumps(context, sort_keys=True, default=str)),
            prompt_hash=_hash(prompt),
            started_at=utcnow(),
            status=ModelInvocationStatus.SUCCEEDED,
        )
        try:
            text = reasoner.complete(prompt)
        except ModelUnavailable as error:
            invocation.status = ModelInvocationStatus.UNAVAILABLE
            invocation.error = f"{error.code}: {error.detail}"[:500]
            invocation.finished_at = utcnow()
            self.database.save_model_invocation(invocation)
            raise
        except Exception as error:  # noqa: BLE001 - every failed call is still a record
            invocation.status = ModelInvocationStatus.FAILED
            invocation.error = f"{type(error).__name__}: {error}"[:500]
            invocation.finished_at = utcnow()
            self.database.save_model_invocation(invocation)
            raise
        invocation.finished_at = utcnow()
        self.database.save_model_invocation(invocation)
        return text, invocation

    def record_decision(
        self,
        invocation: ModelInvocation,
        *,
        decision_type: str,
        alternatives: list[dict[str, Any]],
        selected_option: str,
        rationale: str,
        evidence_ids: list[UUID] | None = None,
    ) -> AIDecision:
        decision = AIDecision(
            mission_id=self.mission_id,
            invocation_id=invocation.id,
            decision_type=decision_type,
            alternatives_considered=alternatives,
            selected_option=selected_option,
            rationale=rationale,
            evidence_ids=list(evidence_ids or []),
        )
        self.database.save_ai_decision(decision)
        return decision


def json_object(text: str) -> dict:
    """Take the first complete JSON object out of a model's answer."""

    decoder = json.JSONDecoder()
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ModelResponseInvalid("the model did not return a JSON object")
