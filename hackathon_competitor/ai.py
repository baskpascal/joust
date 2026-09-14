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


class Reasoner(Protocol):
    """A text-in/text-out model. Implementations must be real providers."""

    provider: str
    model: str

    def complete(self, prompt: str) -> str: ...


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
    ):
        self.executable = executable
        self.provider = "claude-code-cli"
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.workdir = Path(workdir).resolve() if workdir else None

    def complete(self, prompt: str) -> str:
        resolved = shutil.which(self.executable)
        if resolved is None:
            raise ModelUnavailable(
                "REASONING_PROVIDER_UNAVAILABLE", f"{self.executable} is not on PATH"
            )
        argv = [resolved, "-p", prompt, "--max-turns", "1"]
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
        if result.returncode != 0:
            raise ModelUnavailable(
                "REASONING_PROVIDER_UNAVAILABLE",
                (result.stderr or result.stdout).strip()[:400] or f"exit {result.returncode}",
            )
        if not result.stdout.strip():
            raise ModelUnavailable("REASONING_PROVIDER_UNAVAILABLE", "provider returned no text")
        return result.stdout


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
    raise ValueError("the model did not return a JSON object")
