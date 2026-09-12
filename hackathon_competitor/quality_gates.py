from __future__ import annotations

from .models import ComplianceReport, Decision, HackathonSpec, QualityGateResult


def rules_gate(spec: HackathonSpec) -> QualityGateResult:
    findings: list[str] = []
    if spec.deadline_at is None and not spec.deadline_explicitly_unknown:
        findings.append("deadline is neither known nor explicitly unknown")
    if not spec.submission_requirements:
        findings.append("submission requirements are missing")
    if not spec.prohibited_actions:
        findings.append("critical prohibitions are missing")
    if not spec.required_technologies:
        findings.append("required technologies are missing")
    return QualityGateResult(name="rules", passed=not findings, blocking_findings=findings)


def strategy_gate(
    decision: Decision | None,
    *,
    differentiation_evidence: bool,
    feasibility_review: bool,
    fallback_strategy: bool,
    risk_register: bool,
    compliance_precheck: bool,
) -> QualityGateResult:
    checks = {
        "selected strategy is missing": decision is not None,
        "evidence-backed differentiation is missing": differentiation_evidence,
        "feasibility review is missing": feasibility_review,
        "fallback strategy is missing": fallback_strategy,
        "risk register is missing": risk_register,
        "rule compliance pre-check is missing": compliance_precheck,
    }
    findings = [message for message, passed in checks.items() if not passed]
    return QualityGateResult(name="strategy", passed=not findings, blocking_findings=findings)


def submission_gate(
    compliance: ComplianceReport,
    *,
    install_tested: bool,
    demo_tested: bool,
    claims_match: bool,
    license_present: bool,
    required_fields_accounted: bool,
) -> QualityGateResult:
    findings = [
        *[f"rule failed: {item}" for item in compliance.blocker_failures],
        *[f"rule unresolved: {item}" for item in compliance.blocker_unknowns],
    ]
    checks = {
        "install/run instructions are untested": install_tested,
        "primary demo path is untested": demo_tested,
        "submission claims outrun implementation": claims_match,
        "MIT license is missing": license_present,
        "required fields are not accounted for": required_fields_accounted,
    }
    findings.extend(message for message, passed in checks.items() if not passed)
    return QualityGateResult(name="submission", passed=not findings, blocking_findings=findings)
