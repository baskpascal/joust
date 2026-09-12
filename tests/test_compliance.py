from uuid import uuid4

from hackathon_competitor.compliance import evaluate_compliance, rules_from_spec
from hackathon_competitor.models import HackathonSpec, Requirement, RuleStatus
from hackathon_competitor.quality_gates import rules_gate, submission_gate


def fixture_spec():
    return HackathonSpec(
        mission_id=uuid4(),
        name="Fixture",
        deadline_explicitly_unknown=True,
        required_technologies=["Use SDK X"],
        prohibited_actions=["No fabricated usage"],
        submission_requirements=[Requirement(id="demo", text="Provide a demo")],
        eligibility_requirements=[Requirement(id="license", text="Use MIT license")],
        rules_locked=True,
    )


def test_rules_gate_requires_complete_rule_shape():
    spec = fixture_spec()
    assert rules_gate(spec).passed
    spec.prohibited_actions = []
    result = rules_gate(spec)
    assert not result.passed
    assert "critical prohibitions are missing" in result.blocking_findings


def test_unknown_blocker_prevents_submission_readiness():
    rules = rules_from_spec(fixture_spec())
    report = evaluate_compliance(rules, {})
    gate = submission_gate(
        report,
        install_tested=True,
        demo_tested=True,
        claims_match=True,
        license_present=True,
        required_fields_accounted=True,
    )
    assert not report.ready
    assert not gate.passed
    assert report.blocker_unknowns


def test_all_blockers_must_pass():
    rules = rules_from_spec(fixture_spec())
    report = evaluate_compliance(rules, {rule.id: RuleStatus.PASS for rule in rules})
    assert report.ready
