from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from go_live_decision_agent.adapters import AdvisoryNote, FixtureAdvisor
from go_live_decision_agent.canonical import canonical_json_bytes, sha256_bytes
from go_live_decision_agent.case_validation import ValidatedCase, validate_case
from go_live_decision_agent.domain import DecisionStatus
from go_live_decision_agent.engine import evaluate_case, verify_packet
from go_live_decision_agent.errors import ValidationError
from go_live_decision_agent.policy import load_policy
from go_live_decision_agent.service import GoLiveDecisionService

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("scenario", "decision", "failed", "blocked"),
    [
        ("pass", DecisionStatus.PASS, (), ()),
        ("blocked", DecisionStatus.BLOCKED, (), ("G-11", "G-13", "G-14")),
        ("fail", DecisionStatus.FAIL, ("G-04", "G-12"), ()),
    ],
)
def test_frozen_decision(
    scenario: str,
    decision: DecisionStatus,
    failed: tuple[str, ...],
    blocked: tuple[str, ...],
) -> None:
    packet, note = GoLiveDecisionService(ROOT / "policy").decide(ROOT / "cases" / scenario)
    assert packet.decision is decision
    assert packet.failed_gate_ids == failed
    assert packet.blocked_gate_ids == blocked
    assert note.decision is decision


def test_explicit_failure_precedes_blocked_evidence() -> None:
    case = validate_case(ROOT / "cases" / "blocked")
    evidence = [dict(item) for item in case.evidence]
    security = next(item for item in evidence if item["gate_id"] == "G-04")
    security["status"] = "FAIL"
    security.pop("payload_sha256")
    security["payload_sha256"] = sha256_bytes(canonical_json_bytes(security))
    modified = ValidatedCase(case.case_dir, case.candidate, tuple(evidence), case.waivers)
    packet = evaluate_case(modified, load_policy(ROOT / "policy"))
    assert packet.decision is DecisionStatus.FAIL
    assert "G-04" in packet.failed_gate_ids


def test_missing_evidence_never_passes() -> None:
    case = validate_case(ROOT / "cases" / "pass")
    evidence = tuple(item for item in case.evidence if item["gate_id"] != "G-01")
    packet = evaluate_case(
        ValidatedCase(case.case_dir, case.candidate, evidence, case.waivers),
        load_policy(ROOT / "policy"),
    )
    assert packet.decision is DecisionStatus.BLOCKED
    assert "G-01" in packet.blocked_gate_ids


def _waiver(
    gate_id: str, authority: str, *, candidate_version: str = "2.0.0-rc.4"
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "approved_at": "2026-07-30",
        "authority": authority,
        "candidate_id": "ATLASBRIDGE-ONBOARDING-2",
        "candidate_version": candidate_version,
        "expires_at": "2026-08-05",
        "gate_id": gate_id,
        "rationale": "Synthetic bounded pilot waiver.",
        "status": "APPROVED",
        "waiver_id": f"W-{gate_id}",
    }
    value["payload_sha256"] = sha256_bytes(canonical_json_bytes(value))
    return value


def test_valid_waiver_can_satisfy_waivable_missing_gate() -> None:
    case = validate_case(ROOT / "cases" / "pass")
    evidence = tuple(item for item in case.evidence if item["gate_id"] != "G-13")
    modified = ValidatedCase(
        case.case_dir, case.candidate, evidence, (_waiver("G-13", "Vendor Manager"),)
    )
    packet = evaluate_case(modified, load_policy(ROOT / "policy"))
    assert packet.decision is DecisionStatus.PASS
    gate = next(item for item in packet.gates if item.gate_id == "G-13")
    assert gate.status.value == "PASS_WITH_WAIVER"


def test_non_waivable_gate_rejects_waiver() -> None:
    case = validate_case(ROOT / "cases" / "pass")
    modified = ValidatedCase(
        case.case_dir, case.candidate, case.evidence, (_waiver("G-04", "Security Lead"),)
    )
    with pytest.raises(ValidationError, match="non-waivable"):
        evaluate_case(modified, load_policy(ROOT / "policy"))


@pytest.mark.parametrize(
    ("gate_id", "authority", "version"),
    [
        ("G-13", "Wrong Authority", "2.0.0-rc.4"),
        ("G-13", "Vendor Manager", "wrong"),
    ],
)
def test_invalid_waiver_does_not_unblock(
    gate_id: str,
    authority: str,
    version: str,
) -> None:
    case = validate_case(ROOT / "cases" / "pass")
    evidence = tuple(item for item in case.evidence if item["gate_id"] != gate_id)
    modified = ValidatedCase(
        case.case_dir,
        case.candidate,
        evidence,
        (_waiver(gate_id, authority, candidate_version=version),),
    )
    packet = evaluate_case(modified, load_policy(ROOT / "policy"))
    assert packet.decision is DecisionStatus.BLOCKED


def test_waiver_cannot_override_explicit_failure() -> None:
    case = validate_case(ROOT / "cases" / "fail")
    modified = ValidatedCase(
        case.case_dir,
        case.candidate,
        case.evidence,
        (_waiver("G-13", "Vendor Manager"),),
    )
    packet = evaluate_case(modified, load_policy(ROOT / "policy"))
    assert packet.decision is DecisionStatus.FAIL


def test_duplicate_evidence_blocks_gate() -> None:
    case = validate_case(ROOT / "cases" / "pass")
    duplicate = copy.deepcopy(dict(case.evidence[0]))
    duplicate["evidence_id"] = "E-DUPLICATE"
    duplicate.pop("payload_sha256")
    duplicate["payload_sha256"] = sha256_bytes(canonical_json_bytes(duplicate))
    modified = ValidatedCase(
        case.case_dir, case.candidate, (*case.evidence, duplicate), case.waivers
    )
    packet = evaluate_case(modified, load_policy(ROOT / "policy"))
    assert packet.decision is DecisionStatus.BLOCKED
    assert "G-01" in packet.blocked_gate_ids


def test_packet_digest_detects_tampering() -> None:
    packet, _ = GoLiveDecisionService(ROOT / "policy").decide(ROOT / "cases" / "pass")
    object.__setattr__(packet, "decision_digest", "0" * 64)
    with pytest.raises(ValidationError, match="digest"):
        verify_packet(packet)


@pytest.mark.parametrize(
    ("authority", "decision_delta", "digest_delta", "message"),
    [
        ("DEPLOY_AUTHORITY", False, False, "authority"),
        ("ADVISORY_ONLY", True, False, "decision"),
        ("ADVISORY_ONLY", False, True, "stale"),
    ],
)
def test_advisor_cannot_override_controls(
    authority: str,
    decision_delta: bool,
    digest_delta: bool,
    message: str,
) -> None:
    baseline, _ = GoLiveDecisionService(ROOT / "policy").decide(ROOT / "cases" / "blocked")
    note = AdvisoryNote(
        adapter_id="malicious-fixture",
        authority=authority,
        decision=DecisionStatus.PASS if decision_delta else baseline.decision,
        decision_digest="0" * 64 if digest_delta else baseline.decision_digest,
        summary="Attempted override.",
    )
    service = GoLiveDecisionService(ROOT / "policy", FixtureAdvisor(note))
    with pytest.raises(ValidationError, match=message):
        service.decide(ROOT / "cases" / "blocked")


def test_runtime_source_does_not_reference_answer_key() -> None:
    for path in (ROOT / "src").rglob("*.py"):
        assert "answer-key" not in path.read_text(encoding="utf-8")
