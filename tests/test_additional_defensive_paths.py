from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from go_live_decision_agent.adapters import AdvisoryNote, verify_advice
from go_live_decision_agent.canonical import canonical_json_bytes, sha256_bytes
from go_live_decision_agent.case_validation import ValidatedCase, validate_case
from go_live_decision_agent.domain import (
    ApprovalState,
    DecisionPacket,
    DecisionStatus,
    EvidenceItem,
    EvidenceStatus,
    GateStatus,
    Waiver,
)
from go_live_decision_agent.engine import _gate_outcome, _valid_waiver, evaluate_case
from go_live_decision_agent.errors import ValidationError
from go_live_decision_agent.policy import load_policy
from go_live_decision_agent.service import GoLiveDecisionService

ROOT = Path(__file__).resolve().parents[1]


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _copy_case(tmp_path: Path, scenario: str = "pass") -> Path:
    target = tmp_path / scenario
    shutil.copytree(ROOT / "cases" / scenario, target)
    return target


def _refresh_manifest_record(case_dir: Path, filename: str) -> None:
    path = case_dir / filename
    manifest_path = case_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for record in manifest["files"]:
        if record["path"] == filename:
            record["bytes"] = path.stat().st_size
            record["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    _write_json(manifest_path, manifest)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("empty-files", "non-empty list"),
        ("non-object-record", "record must be an object"),
        ("duplicate-path", "duplicate manifest path"),
        ("missing-file", "missing or unsafe"),
        ("wrong-bytes", "byte count mismatch"),
        ("wrong-digest", "digest mismatch"),
        ("incomplete-coverage", "coverage mismatch"),
    ],
)
def test_manifest_shape_and_integrity_fail_closed(
    tmp_path: Path,
    mutation: str,
    message: str,
) -> None:
    target = _copy_case(tmp_path)
    path = target / "manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if mutation == "empty-files":
        payload["files"] = []
    elif mutation == "non-object-record":
        payload["files"][0] = "invalid"
    elif mutation == "duplicate-path":
        payload["files"][1]["path"] = payload["files"][0]["path"]
    elif mutation == "missing-file":
        (target / payload["files"][0]["path"]).unlink()
    elif mutation == "wrong-bytes":
        payload["files"][0]["bytes"] += 1
    elif mutation == "wrong-digest":
        payload["files"][0]["sha256"] = "0" * 64
    elif mutation == "incomplete-coverage":
        payload["files"].pop()
    else:  # pragma: no cover - parametrization is exhaustive
        raise AssertionError(mutation)
    _write_json(path, payload)
    with pytest.raises(ValidationError, match=message):
        validate_case(target)


def test_non_object_evidence_and_waiver_fail_closed(tmp_path: Path) -> None:
    evidence_case = _copy_case(tmp_path / "evidence")
    evidence_path = evidence_case / "evidence.json"
    evidence_payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence_payload["evidence"][0] = "invalid"
    _write_json(evidence_path, evidence_payload)
    _refresh_manifest_record(evidence_case, "evidence.json")
    with pytest.raises(ValidationError, match="evidence item"):
        validate_case(evidence_case)

    waiver_case = _copy_case(tmp_path / "waiver", "blocked")
    waiver_path = waiver_case / "waivers.json"
    waiver_payload = {"waivers": ["invalid"]}
    _write_json(waiver_path, waiver_payload)
    _refresh_manifest_record(waiver_case, "waivers.json")
    with pytest.raises(ValidationError, match="waiver must be an object"):
        validate_case(waiver_case)


def test_inconsistent_scenario_fails_closed(tmp_path: Path) -> None:
    target = _copy_case(tmp_path)
    path = target / "candidate.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["scenario"] = "blocked"
    _write_json(path, payload)
    _refresh_manifest_record(target, "candidate.json")
    with pytest.raises(ValidationError, match="scenario"):
        validate_case(target)


def _copy_policy(tmp_path: Path) -> Path:
    target = tmp_path / "policy"
    shutil.copytree(ROOT / "policy", target)
    return target


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing-gates", "gates list"),
        ("non-object-gate", "gate policy must be an object"),
        ("empty-id", "non-empty string"),
        ("duplicate-id", "duplicate gate"),
        ("optional", "mandatory"),
        ("cardinality", "cardinality"),
    ],
)
def test_policy_shape_fail_closed(tmp_path: Path, mutation: str, message: str) -> None:
    target = _copy_policy(tmp_path)
    path = target / "gates.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if mutation == "missing-gates":
        payload.pop("gates")
    elif mutation == "non-object-gate":
        payload["gates"][0] = "invalid"
    elif mutation == "empty-id":
        payload["gates"][0]["gate_id"] = ""
    elif mutation == "duplicate-id":
        payload["gates"][1]["gate_id"] = payload["gates"][0]["gate_id"]
    elif mutation == "optional":
        payload["gates"][0]["criticality"] = "OPTIONAL"
    elif mutation == "cardinality":
        payload["gates"][0]["evidence_cardinality"] = "AT_LEAST_ONE"
    else:  # pragma: no cover - parametrization is exhaustive
        raise AssertionError(mutation)
    _write_json(path, payload)
    with pytest.raises(ValidationError, match=message):
        load_policy(target)


def test_invalid_policy_json_fails_closed(tmp_path: Path) -> None:
    target = _copy_policy(tmp_path)
    (target / "gates.json").write_text("{", encoding="utf-8")
    with pytest.raises(ValidationError, match="invalid policy"):
        load_policy(target)


def _evidence_item(*, expires_at: str = "2026-12-31") -> EvidenceItem:
    return EvidenceItem(
        evidence_id="E-TEST",
        gate_id="G-01",
        title="Test evidence",
        status=EvidenceStatus.PASS,
        approval_state=ApprovalState.APPROVED,
        observed_at="2026-07-30",
        expires_at=expires_at,
        owner="Release Manager",
        issuer="Synthetic test",
        candidate_id="ATLASBRIDGE-ONBOARDING-2",
        candidate_version="2.0.0-rc.4",
        assertion="Test assertion",
        source_type="SYNTHETIC",
        payload_sha256="0" * 64,
    )


def test_invalid_evidence_expiry_reaches_fail_closed_guard() -> None:
    policy = load_policy(ROOT / "policy")
    gate = policy.gates_by_id["G-01"]
    with pytest.raises(ValidationError, match="invalid evidence date"):
        _gate_outcome(
            gate,
            (_evidence_item(expires_at="invalid"),),
            (),
            candidate_id="ATLASBRIDGE-ONBOARDING-2",
            candidate_version="2.0.0-rc.4",
            assessment_date=date(2026, 8, 1),
        )


def test_waiver_validation_rejects_mismatch_and_invalid_dates() -> None:
    waiver = Waiver(
        waiver_id="W-TEST",
        gate_id="G-13",
        candidate_id="ATLASBRIDGE-ONBOARDING-2",
        candidate_version="2.0.0-rc.4",
        authority="Vendor Manager",
        rationale="Bounded synthetic test",
        approved_at="2026-07-30",
        expires_at="2026-08-05",
        status="APPROVED",
        payload_sha256="0" * 64,
    )
    assessment = date(2026, 8, 1)
    assert not _valid_waiver(
        waiver,
        gate_id="G-11",
        candidate_id=waiver.candidate_id,
        candidate_version=waiver.candidate_version,
        assessment_date=assessment,
        owner_role=waiver.authority,
    )
    assert not _valid_waiver(
        waiver,
        gate_id=waiver.gate_id,
        candidate_id="other",
        candidate_version=waiver.candidate_version,
        assessment_date=assessment,
        owner_role=waiver.authority,
    )
    assert not _valid_waiver(
        replace(waiver, status="PENDING"),
        gate_id=waiver.gate_id,
        candidate_id=waiver.candidate_id,
        candidate_version=waiver.candidate_version,
        assessment_date=assessment,
        owner_role=waiver.authority,
    )
    with pytest.raises(ValidationError, match="invalid waiver date"):
        _valid_waiver(
            replace(waiver, approved_at="invalid"),
            gate_id=waiver.gate_id,
            candidate_id=waiver.candidate_id,
            candidate_version=waiver.candidate_version,
            assessment_date=assessment,
            owner_role=waiver.authority,
        )


def _signed_waiver(gate_id: str, authority: str, waiver_id: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "approved_at": "2026-07-30",
        "authority": authority,
        "candidate_id": "ATLASBRIDGE-ONBOARDING-2",
        "candidate_version": "2.0.0-rc.4",
        "expires_at": "2026-08-05",
        "gate_id": gate_id,
        "rationale": "Bounded synthetic test",
        "status": "APPROVED",
        "waiver_id": waiver_id,
    }
    payload["payload_sha256"] = sha256_bytes(canonical_json_bytes(payload))
    return payload


def test_multiple_applicable_waivers_remain_blocked() -> None:
    case = validate_case(ROOT / "cases" / "blocked")
    waivers = (
        _signed_waiver("G-13", "Vendor Manager", "W-1"),
        _signed_waiver("G-13", "Vendor Manager", "W-2"),
    )
    packet = evaluate_case(
        ValidatedCase(case.case_dir, case.candidate, case.evidence, waivers),
        load_policy(ROOT / "policy"),
    )
    outcome = next(gate for gate in packet.gates if gate.gate_id == "G-13")
    assert outcome.status is GateStatus.BLOCKED
    assert "MULTIPLE_APPLICABLE_WAIVERS" in outcome.reason_codes


def test_evaluate_case_rejects_invalid_assessment_and_unknown_waiver_gate() -> None:
    case = validate_case(ROOT / "cases" / "pass")
    with pytest.raises(ValidationError, match="assessment date"):
        evaluate_case(
            ValidatedCase(
                case.case_dir,
                {**case.candidate, "assessment_date": "invalid"},
                case.evidence,
                case.waivers,
            ),
            load_policy(ROOT / "policy"),
        )
    with pytest.raises(ValidationError, match="unknown gate"):
        evaluate_case(
            ValidatedCase(
                case.case_dir,
                case.candidate,
                case.evidence,
                (_signed_waiver("G-99", "Unknown", "W-99"),),
            ),
            load_policy(ROOT / "policy"),
        )


def test_empty_advisory_summary_is_rejected() -> None:
    packet, _ = GoLiveDecisionService(ROOT / "policy").decide(ROOT / "cases" / "pass")
    with pytest.raises(ValidationError, match="summary"):
        verify_advice(
            packet,
            AdvisoryNote(
                adapter_id="empty-fixture",
                decision=DecisionStatus.PASS,
                decision_digest=packet.decision_digest,
                summary=" ",
            ),
        )


def test_case_and_policy_symlink_boundaries(tmp_path: Path) -> None:
    case_link = tmp_path / "case-link"
    case_link.symlink_to(ROOT / "cases" / "pass", target_is_directory=True)
    with pytest.raises(ValidationError, match="case directory"):
        validate_case(case_link)

    policy_link = tmp_path / "policy-link"
    policy_link.symlink_to(ROOT / "policy", target_is_directory=True)
    with pytest.raises(ValidationError, match="policy directory"):
        load_policy(policy_link)

    copied = _copy_policy(tmp_path / "file-link")
    gates = copied / "gates.json"
    real = copied / "gates-real.json"
    gates.rename(real)
    gates.symlink_to(real.name)
    with pytest.raises(ValidationError, match="policy file"):
        load_policy(copied)


def test_evidence_required_text_and_date_order_fail_closed(tmp_path: Path) -> None:
    for field, value, message in [
        ("title", "", "non-empty string"),
        ("expires_at", "2026-07-01", "expires before observation"),
    ]:
        target = _copy_case(tmp_path / field)
        path = target / "evidence.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        item = payload["evidence"][0]
        item[field] = value
        unsigned = dict(item)
        unsigned.pop("payload_sha256")
        item["payload_sha256"] = sha256_bytes(canonical_json_bytes(unsigned))
        _write_json(path, payload)
        _refresh_manifest_record(target, "evidence.json")
        with pytest.raises(ValidationError, match=message):
            validate_case(target)


def test_future_dated_evidence_blocks_pass() -> None:
    case = validate_case(ROOT / "cases" / "pass")
    evidence = [dict(item) for item in case.evidence]
    evidence[0]["observed_at"] = "2026-08-02"
    evidence[0]["expires_at"] = "2026-12-31"
    unsigned = dict(evidence[0])
    unsigned.pop("payload_sha256")
    evidence[0]["payload_sha256"] = sha256_bytes(canonical_json_bytes(unsigned))
    packet = evaluate_case(
        ValidatedCase(case.case_dir, case.candidate, tuple(evidence), case.waivers),
        load_policy(ROOT / "policy"),
    )
    outcome = next(gate for gate in packet.gates if gate.gate_id == "G-01")
    assert packet.decision is DecisionStatus.BLOCKED
    assert "EVIDENCE_FROM_FUTURE" in outcome.reason_codes


def test_policy_requires_exact_gate_identifiers_and_valid_enums(tmp_path: Path) -> None:
    target = _copy_policy(tmp_path / "ids")
    path = target / "gates.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["gates"][0]["gate_id"] = "G-99"
    _write_json(path, payload)
    with pytest.raises(ValidationError, match="G-01 through G-14"):
        load_policy(target)

    target = _copy_policy(tmp_path / "enum")
    path = target / "gates.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["gates"][0]["waiver_policy"] = "UNKNOWN"
    _write_json(path, payload)
    with pytest.raises(ValidationError, match="enumeration"):
        load_policy(target)


def _redigest(packet: DecisionPacket) -> DecisionPacket:
    return replace(
        packet,
        decision_digest=sha256_bytes(canonical_json_bytes(packet.as_dict(include_digest=False))),
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("failed-index", "failed gate index"),
        ("blocked-index", "blocked gate index"),
        ("passed-index", "passed gate index"),
        ("missing-waiver-id", "no waiver identifier"),
        ("unexpected-waiver-id", "non-waived gate"),
        ("duplicate-gate", "fourteen unique"),
    ],
)
def test_packet_structural_tampering_is_rejected(mutation: str, message: str) -> None:
    from go_live_decision_agent.engine import verify_packet

    packet = GoLiveDecisionService(ROOT / "policy").decide(ROOT / "cases" / "pass")[0]
    if mutation == "failed-index":
        changed = replace(packet, failed_gate_ids=("G-01",))
    elif mutation == "blocked-index":
        changed = replace(packet, blocked_gate_ids=("G-01",))
    elif mutation == "passed-index":
        changed = replace(packet, passed_gate_ids=packet.passed_gate_ids[:-1])
    elif mutation == "missing-waiver-id":
        waived_case = validate_case(ROOT / "cases" / "pass")
        evidence = tuple(item for item in waived_case.evidence if item["gate_id"] != "G-13")
        waived = evaluate_case(
            ValidatedCase(
                waived_case.case_dir,
                waived_case.candidate,
                evidence,
                (_signed_waiver("G-13", "Vendor Manager", "W-13"),),
            ),
            load_policy(ROOT / "policy"),
        )
        gates = tuple(
            replace(gate, waiver_id=None) if gate.gate_id == "G-13" else gate
            for gate in waived.gates
        )
        changed = replace(waived, gates=gates)
    elif mutation == "unexpected-waiver-id":
        gates = (replace(packet.gates[0], waiver_id="W-UNEXPECTED"), *packet.gates[1:])
        changed = replace(packet, gates=gates)
    elif mutation == "duplicate-gate":
        gates = (packet.gates[0], packet.gates[0], *packet.gates[2:])
        changed = replace(packet, gates=gates)
    else:  # pragma: no cover - parametrization is exhaustive
        raise AssertionError(mutation)
    with pytest.raises(ValidationError, match=message):
        verify_packet(_redigest(changed))


def test_secret_scan_excludes_only_verified_generated_digest_fixtures() -> None:
    from scripts.secret_scan import candidate_paths

    paths = {path.as_posix() for path in candidate_paths()}
    assert not any(path.startswith("expected/") for path in paths)
    assert not any(path.startswith("src/go_live_decision_agent/sample_cases/") for path in paths)
    assert "src/go_live_decision_agent/engine.py" in paths
    assert "scripts/secret_scan.py" in paths
