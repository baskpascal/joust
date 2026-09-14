from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any
from uuid import UUID

from .competition_rules import CompetitionRuleService
from .models import (
    CompetitionRule,
    CompetitionRuleStatus,
    CurrentCompetitionState,
    DeadlineSignal,
    Evidence,
    Extraction,
    LeaderboardSignal,
    MetricSignal,
    RuleObservation,
    SourceObservation,
    StructuredSignal,
    StructuredSignalType,
    utcnow,
)
from .storage import Database


AUTHORITY_PRIORITY = {
    "ORGANIZER_ANNOUNCEMENT": 700,
    "OFFICIAL_RULES": 600,
    "OFFICIAL_DOCS": 500,
    "ORGANIZER_STATEMENT": 400,
    "PLATFORM_METADATA": 300,
    "INFERRED": 200,
    "THIRD_PARTY": 100,
}

SIGNAL_MODELS: dict[StructuredSignalType, type[StructuredSignal]] = {
    StructuredSignalType.RULE: RuleObservation,
    StructuredSignalType.METRIC: MetricSignal,
    StructuredSignalType.DEADLINE: DeadlineSignal,
    StructuredSignalType.LEADERBOARD: LeaderboardSignal,
}


def authority_priority(authority: str) -> int:
    normalized = authority.strip().upper().replace(" ", "_").replace("-", "_")
    aliases = {
        "OFFICIAL": "OFFICIAL_RULES",
        "NEW_ORGANIZER_ANNOUNCEMENT": "ORGANIZER_ANNOUNCEMENT",
        "OFFICIAL_COMPETITION_RULES": "OFFICIAL_RULES",
        "OFFICIAL_DOCUMENTATION": "OFFICIAL_DOCS",
    }
    return AUTHORITY_PRIORITY.get(aliases.get(normalized, normalized), 0)


class CompetitionIntelligence:
    """Durable source-to-state pipeline with deterministic reconciliation."""

    def __init__(self, database: Database):
        self.database = database

    def observe_source(
        self,
        *,
        mission_id: UUID,
        source_uri: str,
        authority: str,
        raw_text: str,
        observed_at: datetime | None = None,
    ) -> SourceObservation:
        if not raw_text.strip():
            raise ValueError("source observation requires non-empty raw text")
        captured_at = observed_at or utcnow()
        evidence = Evidence(
            mission_id=mission_id,
            claim=f"Raw competition source observed at {source_uri}",
            source_type="source_observation",
            source_uri=source_uri,
            excerpt=raw_text[:500],
            confidence=1.0,
            authority=authority,
            retrieved_at=captured_at,
        )
        self.database.save_evidence(evidence)
        observation = SourceObservation(
            mission_id=mission_id,
            source_uri=source_uri,
            authority=authority,
            observed_at=captured_at,
            raw_text=raw_text,
            content_hash=hashlib.sha256(raw_text.encode()).hexdigest(),
            evidence_id=evidence.id,
        )
        self.database.save_source_observation(observation)
        self.database.append_event(
            mission_id,
            "SOURCE_OBSERVATION_RECORDED",
            {
                "source_observation_id": str(observation.id),
                "evidence_id": str(evidence.id),
                "content_hash": observation.content_hash,
            },
        )
        return observation

    def extract(
        self,
        source_observation_id: UUID,
        signal_payloads: list[dict[str, Any]],
        *,
        extractor: str,
        extractor_version: str,
    ) -> Extraction:
        observation = self.database.get_source_observation(source_observation_id)
        extraction = Extraction(
            mission_id=observation.mission_id,
            source_observation_id=observation.id,
            extractor=extractor,
            extractor_version=extractor_version,
        )
        signals: list[StructuredSignal] = []
        for payload in signal_payloads:
            kind = StructuredSignalType(payload["signal_type"])
            model = SIGNAL_MODELS[kind]
            signals.append(
                model.model_validate(
                    {
                        **payload,
                        "mission_id": observation.mission_id,
                        "extraction_id": extraction.id,
                        "source_observation_id": observation.id,
                        "source_evidence_id": observation.evidence_id,
                        "observed_at": observation.observed_at,
                        "authority": payload.get("authority", observation.authority),
                    }
                )
            )
        extraction.signal_ids = [signal.id for signal in signals]
        self.database.save_extraction(extraction)
        for signal in signals:
            self.database.save_structured_signal(signal)
        self.database.append_event(
            observation.mission_id,
            "STRUCTURED_SIGNALS_EXTRACTED",
            {
                "extraction_id": str(extraction.id),
                "source_observation_id": str(observation.id),
                "signal_ids": [str(item) for item in extraction.signal_ids],
            },
        )
        return extraction

    def reconcile(self, mission_id: UUID) -> CurrentCompetitionState:
        signals = self.database.list_structured_signals(mission_id)
        if not signals:
            raise ValueError("reconciliation requires at least one structured signal")

        conflicts: list[str] = []
        selected_signal_ids: list[UUID] = []
        for signal in (item for item in signals if isinstance(item, RuleObservation)):
            _, conflict = self._reconcile_rule(signal)
            if conflict:
                conflicts.append(conflict)

        active_rules = [
            item
            for item in self.database.list_competition_rules(mission_id)
            if item.status == CompetitionRuleStatus.ACTIVE
        ]
        for rule in active_rules:
            matching_signal = next(
                (
                    item
                    for item in signals
                    if isinstance(item, RuleObservation)
                    and item.source_observation_id == rule.source_id
                    and item.category == rule.category
                    and item.normalized_constraint == rule.normalized_constraint
                ),
                None,
            )
            if matching_signal is not None:
                selected_signal_ids.append(matching_signal.id)

        metrics: dict[str, float] = {}
        deadlines: dict[str, datetime] = {}
        leaderboard: dict[str, dict[str, int | None]] = {}
        winners: dict[tuple[str, str], StructuredSignal] = {}
        for signal in signals:
            if isinstance(signal, RuleObservation):
                continue
            if isinstance(signal, MetricSignal):
                key = (signal.signal_type.value, signal.metric)
            elif isinstance(signal, DeadlineSignal):
                key = (signal.signal_type.value, signal.deadline_type)
            elif isinstance(signal, LeaderboardSignal):
                key = (signal.signal_type.value, signal.agent_id)
            else:  # pragma: no cover - storage only returns known signal contracts
                continue
            current = winners.get(key)
            if current is None or self._wins(signal, current):
                winners[key] = signal

        for signal in winners.values():
            selected_signal_ids.append(signal.id)
            if isinstance(signal, MetricSignal):
                metrics[signal.metric] = signal.value
            elif isinstance(signal, DeadlineSignal):
                deadlines[signal.deadline_type] = signal.deadline_at
            elif isinstance(signal, LeaderboardSignal):
                leaderboard[signal.agent_id] = {
                    "rank": signal.rank,
                    "users": signal.users,
                    "successful_installs": signal.successful_installs,
                    "token_usage": signal.token_usage,
                }

        prior = self.database.list_current_competition_states(mission_id)
        state = CurrentCompetitionState(
            mission_id=mission_id,
            version=max((item.version for item in prior), default=0) + 1,
            active_rule_ids=[item.id for item in active_rules],
            signal_ids=selected_signal_ids,
            metrics=metrics,
            deadlines=deadlines,
            leaderboard=leaderboard,
            conflicts=conflicts,
        )
        self.database.save_current_competition_state(state)
        self.database.append_event(
            mission_id,
            "COMPETITION_STATE_RECONCILED",
            {
                "state_id": str(state.id),
                "version": state.version,
                "active_rule_ids": [str(item) for item in state.active_rule_ids],
                "conflicts": state.conflicts,
            },
        )
        return state

    @staticmethod
    def _wins(candidate: StructuredSignal, current: StructuredSignal) -> bool:
        return (authority_priority(candidate.authority), candidate.observed_at) >= (
            authority_priority(current.authority),
            current.observed_at,
        )

    def _reconcile_rule(self, signal: RuleObservation) -> tuple[CompetitionRule, str | None]:
        rules = self.database.list_competition_rules(signal.mission_id)
        existing = next(
            (
                rule
                for rule in rules
                if rule.source_id == signal.source_observation_id
                and rule.category == signal.category
                and rule.normalized_constraint == signal.normalized_constraint
            ),
            None,
        )
        if existing is not None:
            return (
                existing,
                None if existing.status != CompetitionRuleStatus.CONFLICTED else existing.statement,
            )

        active = [
            rule
            for rule in rules
            if rule.category == signal.category and rule.status == CompetitionRuleStatus.ACTIVE
        ]
        prior = max(active, key=lambda item: item.observed_at) if active else None
        rule = CompetitionRule(
            mission_id=signal.mission_id,
            source_id=signal.source_observation_id,
            observed_at=signal.observed_at,
            category=signal.category,
            statement=signal.statement,
            normalized_constraint=signal.normalized_constraint,
            authority=signal.authority,
            confidence=signal.confidence,
        )
        if prior is None or prior.normalized_constraint == rule.normalized_constraint:
            return CompetitionRuleService(self.database).record(rule), None
        if (
            authority_priority(rule.authority) >= authority_priority(prior.authority)
            and rule.observed_at >= prior.observed_at
        ):
            rule.supersedes_rule_id = prior.id
            return CompetitionRuleService(self.database).record(rule), None

        rule.status = CompetitionRuleStatus.CONFLICTED
        self.database.save_competition_rule(rule)
        self.database.append_event(
            signal.mission_id,
            "COMPETITION_RULE_CONFLICTED",
            {"rule_id": str(rule.id), "active_rule_id": str(prior.id)},
        )
        return rule, f"{rule.category}: {rule.statement}"
