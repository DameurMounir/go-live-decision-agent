from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from go_live_decision_agent.adapters import RuleAdvisor
from go_live_decision_agent.canonical import canonical_json_bytes, sha256_bytes
from go_live_decision_agent.case_validation import ValidatedCase, validate_case
from go_live_decision_agent.domain import (
    DecisionStatus,
    ReviewAction,
    ReviewState,
    require_mapping,
    string_tuple,
)
from go_live_decision_agent.engine import evaluate_case
from go_live_decision_agent.errors import ReviewConflictError, ValidationError
from go_live_decision_agent.policy import load_policy
from go_live_decision_agent.review import state_for_action
from go_live_decision_agent.serialization import packet_from_dict
from go_live_decision_agent.service import GoLiveDecisionService
from go_live_decision_agent.store import ReviewStore

ROOT = Path(__file__).resolve().parents[1]


def _rewrite_manifest(case_dir: Path, filename: str) -> None:
    path = case_dir / filename
    manifest_path = case_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for record in manifest["files"]:
        if record["path"] == filename:
            record["bytes"] = path.stat().st_size
            record["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def _copy(tmp_path: Path, scenario: str = "pass") -> Path:
    target = tmp_path / scenario
    shutil.copytree(ROOT / "cases" / scenario, target)
    return target


@pytest.mark.parametrize(
    ("file", "payload", "message"),
    [
        ("manifest.json", [], "manifest"),
        ("candidate.json", [], "candidate"),
        ("evidence.json", [], "evidence"),
        ("waivers.json", [], "waivers"),
    ],
)
def test_invalid_top_level_shapes(tmp_path: Path, file: str, payload: object, message: str) -> None:
    target = _copy(tmp_path)
    (target / file).write_text(json.dumps(payload) + "\n")
    if file != "manifest.json":
        _rewrite_manifest(target, file)
    with pytest.raises(ValidationError, match=message):
        validate_case(target)


def test_invalid_json_is_rejected(tmp_path: Path) -> None:
    target = _copy(tmp_path)
    (target / "candidate.json").write_text("{")
    _rewrite_manifest(target, "candidate.json")
    with pytest.raises(ValidationError, match="invalid JSON"):
        validate_case(target)


def test_missing_case_directory_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="missing"):
        validate_case(tmp_path / "missing")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("gate_id", "BAD", "gate identifier"),
        ("status", "UNKNOWN", "status"),
        ("approval_state", "UNKNOWN", "approval"),
        ("candidate_id", "WRONG", "candidate mismatch"),
        ("observed_at", "not-a-date", "date"),
    ],
)
def test_invalid_evidence_fields(tmp_path: Path, field: str, value: str, message: str) -> None:
    target = _copy(tmp_path)
    path = target / "evidence.json"
    payload = json.loads(path.read_text())
    item = payload["evidence"][0]
    item[field] = value
    unsigned = dict(item)
    unsigned.pop("payload_sha256")
    item["payload_sha256"] = sha256_bytes(canonical_json_bytes(unsigned))
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    _rewrite_manifest(target, "evidence.json")
    with pytest.raises(ValidationError, match=message):
        validate_case(target)


def test_duplicate_evidence_identifier_is_rejected(tmp_path: Path) -> None:
    target = _copy(tmp_path)
    path = target / "evidence.json"
    payload = json.loads(path.read_text())
    duplicate = dict(payload["evidence"][1])
    duplicate["evidence_id"] = payload["evidence"][0]["evidence_id"]
    duplicate.pop("payload_sha256")
    duplicate["payload_sha256"] = sha256_bytes(canonical_json_bytes(duplicate))
    payload["evidence"].append(duplicate)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    _rewrite_manifest(target, "evidence.json")
    with pytest.raises(ValidationError, match="duplicate evidence"):
        validate_case(target)


def test_invalid_assessment_date_is_rejected(tmp_path: Path) -> None:
    target = _copy(tmp_path)
    path = target / "candidate.json"
    payload = json.loads(path.read_text())
    payload["assessment_date"] = "bad"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    _rewrite_manifest(target, "candidate.json")
    with pytest.raises(ValidationError, match="assessment_date"):
        validate_case(target)


def test_unknown_evidence_gate_is_rejected() -> None:
    case = validate_case(ROOT / "cases" / "pass")
    evidence = [dict(item) for item in case.evidence]
    evidence[0]["gate_id"] = "G-99"
    modified = ValidatedCase(case.case_dir, case.candidate, tuple(evidence), case.waivers)
    with pytest.raises(ValidationError, match="unknown gate"):
        evaluate_case(modified, load_policy(ROOT / "policy"))


def test_rejected_evidence_blocks() -> None:
    case = validate_case(ROOT / "cases" / "pass")
    evidence = [dict(item) for item in case.evidence]
    evidence[0]["approval_state"] = "REJECTED"
    packet = evaluate_case(
        ValidatedCase(case.case_dir, case.candidate, tuple(evidence), case.waivers),
        load_policy(ROOT / "policy"),
    )
    assert packet.decision is DecisionStatus.BLOCKED


def test_owner_mismatch_blocks() -> None:
    case = validate_case(ROOT / "cases" / "pass")
    evidence = [dict(item) for item in case.evidence]
    evidence[0]["owner"] = "Wrong Owner"
    packet = evaluate_case(
        ValidatedCase(case.case_dir, case.candidate, tuple(evidence), case.waivers),
        load_policy(ROOT / "policy"),
    )
    assert packet.decision is DecisionStatus.BLOCKED


def test_waiver_missing_fields_is_rejected() -> None:
    case = validate_case(ROOT / "cases" / "pass")
    modified = ValidatedCase(case.case_dir, case.candidate, case.evidence, ({"waiver_id": "W"},))
    with pytest.raises(ValidationError, match="fields missing"):
        evaluate_case(modified, load_policy(ROOT / "policy"))


def test_waiver_digest_is_rejected() -> None:
    case = validate_case(ROOT / "cases" / "pass")
    waiver = {
        "approved_at": "2026-07-30",
        "authority": "Vendor Manager",
        "candidate_id": "ATLASBRIDGE-ONBOARDING-2",
        "candidate_version": "2.0.0-rc.4",
        "expires_at": "2026-08-05",
        "gate_id": "G-13",
        "payload_sha256": "0" * 64,
        "rationale": "test",
        "status": "APPROVED",
        "waiver_id": "W-13",
    }
    with pytest.raises(ValidationError, match="digest"):
        evaluate_case(
            ValidatedCase(case.case_dir, case.candidate, case.evidence, (waiver,)),
            load_policy(ROOT / "policy"),
        )


def test_domain_helpers_fail_closed() -> None:
    with pytest.raises(ValueError, match="strings"):
        string_tuple(["ok", ""], "items")
    with pytest.raises(ValueError, match="mapping"):
        require_mapping([], "value")


def test_review_action_states() -> None:
    assert state_for_action(ReviewAction.CONFIRM) is ReviewState.CONFIRMED
    assert state_for_action(ReviewAction.REQUEST_REVISION) is ReviewState.REVISION_REQUESTED
    assert state_for_action(ReviewAction.REJECT) is ReviewState.REJECTED


def test_rule_advisor_summary() -> None:
    packet, _ = GoLiveDecisionService(ROOT / "policy").decide(ROOT / "cases" / "pass")
    assert "PASS" in RuleAdvisor().advise(packet).summary


def test_serialization_requires_gate_list() -> None:
    with pytest.raises(ValueError, match="gates"):
        packet_from_dict({})


def test_store_run_conflict_and_unknown_paths(tmp_path: Path) -> None:
    store = ReviewStore(tmp_path / "review.sqlite3")
    pass_packet = GoLiveDecisionService(ROOT / "policy").decide(ROOT / "cases" / "pass")[0]
    fail_packet = GoLiveDecisionService(ROOT / "policy").decide(ROOT / "cases" / "fail")[0]
    store.create_run("RUN-1", pass_packet)
    store.create_run("RUN-1", pass_packet)
    with pytest.raises(ReviewConflictError, match="another packet"):
        store.create_run("RUN-1", fail_packet)
    with pytest.raises(ReviewConflictError, match="unknown run"):
        store.load_packet("missing")
    with pytest.raises(ReviewConflictError, match="unknown run"):
        store.issue_challenge("missing", pass_packet.decision_digest)


@pytest.mark.parametrize(
    ("reviewer", "comment", "message"),
    [
        ("", "", "reviewer"),
        ("Reviewer", "x" * 2001, "comment"),
    ],
)
def test_review_field_validation(tmp_path: Path, reviewer: str, comment: str, message: str) -> None:
    store = ReviewStore(tmp_path / "review.sqlite3")
    packet = GoLiveDecisionService(ROOT / "policy").decide(ROOT / "cases" / "pass")[0]
    store.create_run("RUN-1", packet)
    challenge = store.issue_challenge(
        "RUN-1", packet.decision_digest, nonce_factory=lambda: "n" * 32
    )
    with pytest.raises(ValidationError, match=message):
        store.record_review(
            run_id="RUN-1",
            decision_digest=packet.decision_digest,
            nonce=challenge.nonce,
            reviewer=reviewer,
            action=ReviewAction.CONFIRM,
            comment=comment,
        )


def test_short_nonce_is_rejected(tmp_path: Path) -> None:
    store = ReviewStore(tmp_path / "review.sqlite3")
    packet = GoLiveDecisionService(ROOT / "policy").decide(ROOT / "cases" / "pass")[0]
    store.create_run("RUN-1", packet)
    with pytest.raises(ValidationError, match="nonce"):
        store.issue_challenge("RUN-1", packet.decision_digest, nonce_factory=lambda: "short")


def test_review_unknown_nonce_and_digest(tmp_path: Path) -> None:
    store = ReviewStore(tmp_path / "review.sqlite3")
    packet = GoLiveDecisionService(ROOT / "policy").decide(ROOT / "cases" / "pass")[0]
    store.create_run("RUN-1", packet)
    with pytest.raises(ReviewConflictError, match="stale"):
        store.record_review(
            run_id="RUN-1",
            decision_digest="0" * 64,
            nonce="x" * 32,
            reviewer="Reviewer",
            action=ReviewAction.CONFIRM,
        )
    with pytest.raises(ReviewConflictError, match="unknown"):
        store.record_review(
            run_id="RUN-1",
            decision_digest=packet.decision_digest,
            nonce="x" * 32,
            reviewer="Reviewer",
            action=ReviewAction.CONFIRM,
        )


def test_stored_packet_shape_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "review.sqlite3"
    store = ReviewStore(path)
    packet = GoLiveDecisionService(ROOT / "policy").decide(ROOT / "cases" / "pass")[0]
    store.create_run("RUN-1", packet)
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("UPDATE runs SET packet_json = '[]' WHERE run_id = 'RUN-1'")
        connection.commit()
    with pytest.raises(ValidationError, match="stored packet"):
        store.load_packet("RUN-1")
