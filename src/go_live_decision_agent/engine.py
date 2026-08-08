from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import replace
from datetime import date
from typing import Any

from .canonical import canonical_json_bytes, sha256_bytes
from .case_validation import ValidatedCase
from .domain import (
    ApprovalState,
    DecisionPacket,
    DecisionStatus,
    EvidenceItem,
    EvidenceStatus,
    GateOutcome,
    GatePolicy,
    GateStatus,
    Waiver,
    WaiverPolicy,
)
from .errors import ValidationError
from .policy import DecisionPolicy

_AUTHORITY_BOUNDARY = (
    "ADVISORY ONLY: the packet evaluates evidence but does not deploy, approve a release "
    "window, waive non-waivable gates, accept risk, or grant go-live authority."
)


def _evidence_from_mapping(value: Mapping[str, Any]) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=str(value["evidence_id"]),
        gate_id=str(value["gate_id"]),
        title=str(value["title"]),
        status=EvidenceStatus(str(value["status"])),
        approval_state=ApprovalState(str(value["approval_state"])),
        observed_at=str(value["observed_at"]),
        expires_at=str(value["expires_at"]),
        owner=str(value["owner"]),
        issuer=str(value["issuer"]),
        candidate_id=str(value["candidate_id"]),
        candidate_version=str(value["candidate_version"]),
        assertion=str(value["assertion"]),
        source_type=str(value["source_type"]),
        payload_sha256=str(value["payload_sha256"]),
    )


def _waiver_from_mapping(value: Mapping[str, Any]) -> Waiver:
    required = {
        "approved_at",
        "authority",
        "candidate_id",
        "candidate_version",
        "expires_at",
        "gate_id",
        "payload_sha256",
        "rationale",
        "status",
        "waiver_id",
    }
    missing = required - set(value)
    if missing:
        raise ValidationError(f"waiver fields missing: {sorted(missing)}")
    unsigned = dict(value)
    digest = str(unsigned.pop("payload_sha256"))
    if digest != sha256_bytes(canonical_json_bytes(unsigned)):
        raise ValidationError(f"waiver payload digest mismatch: {value['waiver_id']}")
    return Waiver(
        waiver_id=str(value["waiver_id"]),
        gate_id=str(value["gate_id"]),
        candidate_id=str(value["candidate_id"]),
        candidate_version=str(value["candidate_version"]),
        authority=str(value["authority"]),
        rationale=str(value["rationale"]),
        approved_at=str(value["approved_at"]),
        expires_at=str(value["expires_at"]),
        status=str(value["status"]),
        payload_sha256=digest,
    )


def _valid_waiver(
    waiver: Waiver,
    *,
    gate_id: str,
    candidate_id: str,
    candidate_version: str,
    assessment_date: date,
    owner_role: str,
) -> bool:
    if waiver.gate_id != gate_id:
        return False
    if waiver.candidate_id != candidate_id or waiver.candidate_version != candidate_version:
        return False
    if waiver.status != "APPROVED" or waiver.authority != owner_role:
        return False
    try:
        approved_at = date.fromisoformat(waiver.approved_at)
        expires_at = date.fromisoformat(waiver.expires_at)
    except ValueError as exc:
        raise ValidationError(f"invalid waiver date: {waiver.waiver_id}") from exc
    if expires_at < approved_at:
        raise ValidationError(f"waiver expires before approval: {waiver.waiver_id}")
    return approved_at <= assessment_date <= expires_at


def _gate_outcome(
    gate: GatePolicy,
    evidence: tuple[EvidenceItem, ...],
    waivers: tuple[Waiver, ...],
    *,
    candidate_id: str,
    candidate_version: str,
    assessment_date: date,
) -> GateOutcome:
    evidence_ids = tuple(sorted(item.evidence_id for item in evidence))

    # Explicit failure dominates every uncertainty and every waiver.
    if any(item.status is EvidenceStatus.FAIL for item in evidence):
        return GateOutcome(
            gate_id=gate.gate_id,
            title=gate.title,
            domain=gate.domain,
            status=GateStatus.FAIL,
            reason_codes=("EXPLICIT_MANDATORY_FAILURE",),
            evidence_ids=evidence_ids,
        )

    reason_codes: list[str] = []
    if not evidence:
        reason_codes.append("MISSING_REQUIRED_EVIDENCE")
    elif len(evidence) != 1:
        reason_codes.append("EVIDENCE_CARDINALITY_CONFLICT")
    else:
        item = evidence[0]
        if item.approval_state is ApprovalState.REJECTED:
            reason_codes.append("EVIDENCE_REJECTED")
        elif item.approval_state is ApprovalState.PENDING:
            reason_codes.append("APPROVAL_PENDING")
        try:
            observed_at = date.fromisoformat(item.observed_at)
            expires_at = date.fromisoformat(item.expires_at)
        except ValueError as exc:
            raise ValidationError(f"invalid evidence date: {item.evidence_id}") from exc
        if expires_at < observed_at:
            raise ValidationError(f"evidence expires before observation: {item.evidence_id}")
        if observed_at > assessment_date:
            reason_codes.append("EVIDENCE_FROM_FUTURE")
        if expires_at < assessment_date:
            reason_codes.append("EVIDENCE_STALE")
        if item.owner != gate.owner_role:
            reason_codes.append("OWNER_MISMATCH")

    if not reason_codes:
        return GateOutcome(
            gate_id=gate.gate_id,
            title=gate.title,
            domain=gate.domain,
            status=GateStatus.PASS,
            reason_codes=("CURRENT_APPROVED_PASS_EVIDENCE",),
            evidence_ids=evidence_ids,
        )

    if gate.waiver_policy is WaiverPolicy.WAIVABLE:
        applicable = [
            waiver
            for waiver in waivers
            if _valid_waiver(
                waiver,
                gate_id=gate.gate_id,
                candidate_id=candidate_id,
                candidate_version=candidate_version,
                assessment_date=assessment_date,
                owner_role=gate.owner_role,
            )
        ]
        if len(applicable) == 1 and set(reason_codes) <= {
            "MISSING_REQUIRED_EVIDENCE",
            "EVIDENCE_STALE",
            "APPROVAL_PENDING",
        }:
            return GateOutcome(
                gate_id=gate.gate_id,
                title=gate.title,
                domain=gate.domain,
                status=GateStatus.PASS_WITH_WAIVER,
                reason_codes=tuple(sorted((*reason_codes, "VALID_BOUNDED_WAIVER"))),
                evidence_ids=evidence_ids,
                waiver_id=applicable[0].waiver_id,
            )
        if len(applicable) > 1:
            reason_codes.append("MULTIPLE_APPLICABLE_WAIVERS")

    return GateOutcome(
        gate_id=gate.gate_id,
        title=gate.title,
        domain=gate.domain,
        status=GateStatus.BLOCKED,
        reason_codes=tuple(sorted(set(reason_codes))),
        evidence_ids=evidence_ids,
    )


def evaluate_case(case: ValidatedCase, policy: DecisionPolicy) -> DecisionPacket:
    candidate_id = str(case.candidate["candidate_id"])
    candidate_version = str(case.candidate["candidate_version"])
    assessment_text = str(case.candidate["assessment_date"])
    try:
        assessment_date = date.fromisoformat(assessment_text)
    except ValueError as exc:
        raise ValidationError("invalid assessment date") from exc

    evidence_by_gate: dict[str, list[EvidenceItem]] = defaultdict(list)
    for raw in case.evidence:
        item = _evidence_from_mapping(raw)
        if item.gate_id not in policy.gates_by_id:
            raise ValidationError(f"evidence references unknown gate: {item.gate_id}")
        evidence_by_gate[item.gate_id].append(item)

    waivers = tuple(_waiver_from_mapping(raw) for raw in case.waivers)
    for waiver in waivers:
        gate = policy.gates_by_id.get(waiver.gate_id)
        if gate is None:
            raise ValidationError(f"waiver references unknown gate: {waiver.gate_id}")
        if gate.waiver_policy is WaiverPolicy.NON_WAIVABLE:
            raise ValidationError(f"waiver targets non-waivable gate: {waiver.gate_id}")

    gates = tuple(
        _gate_outcome(
            gate,
            tuple(evidence_by_gate.get(gate.gate_id, [])),
            waivers,
            candidate_id=candidate_id,
            candidate_version=candidate_version,
            assessment_date=assessment_date,
        )
        for gate in policy.gates
    )
    failed = tuple(gate.gate_id for gate in gates if gate.status is GateStatus.FAIL)
    blocked = tuple(gate.gate_id for gate in gates if gate.status is GateStatus.BLOCKED)
    passed = tuple(
        gate.gate_id
        for gate in gates
        if gate.status in {GateStatus.PASS, GateStatus.PASS_WITH_WAIVER}
    )
    if failed:
        decision = DecisionStatus.FAIL
    elif blocked:
        decision = DecisionStatus.BLOCKED
    else:
        decision = DecisionStatus.PASS

    residual_risks = tuple(
        f"{gate.gate_id}: bounded waiver accepted for {gate.title}"
        for gate in gates
        if gate.status is GateStatus.PASS_WITH_WAIVER
    )
    required_actions = (
        *(f"Remediate failed gate {gate_id} before reconsideration." for gate_id in failed),
        *(f"Supply or reconcile evidence for blocked gate {gate_id}." for gate_id in blocked),
    )
    packet = DecisionPacket(
        candidate_id=candidate_id,
        candidate_version=candidate_version,
        scenario=str(case.candidate["scenario"]),
        assessment_date=assessment_text,
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        decision=decision,
        gates=gates,
        failed_gate_ids=failed,
        blocked_gate_ids=blocked,
        passed_gate_ids=passed,
        residual_risks=residual_risks,
        required_actions=required_actions,
        limitations=(
            "The organisation, candidate, evidence, and outcomes are synthetic.",
            "The decision is evidence-bound and is not a production forecast.",
            "Human release authority remains responsible for the actual go-live decision.",
        ),
        authority_boundary=_AUTHORITY_BOUNDARY,
    )
    return replace(
        packet,
        decision_digest=sha256_bytes(canonical_json_bytes(packet.as_dict(include_digest=False))),
    )


def verify_packet(packet: DecisionPacket) -> None:
    expected = sha256_bytes(canonical_json_bytes(packet.as_dict(include_digest=False)))
    if packet.decision_digest != expected:
        raise ValidationError("decision packet digest mismatch")

    gate_ids = tuple(gate.gate_id for gate in packet.gates)
    if len(gate_ids) != 14 or len(set(gate_ids)) != 14:
        raise ValidationError("decision packet must contain fourteen unique gate outcomes")
    actual_failed = tuple(gate.gate_id for gate in packet.gates if gate.status is GateStatus.FAIL)
    actual_blocked = tuple(
        gate.gate_id for gate in packet.gates if gate.status is GateStatus.BLOCKED
    )
    actual_passed = tuple(
        gate.gate_id
        for gate in packet.gates
        if gate.status in {GateStatus.PASS, GateStatus.PASS_WITH_WAIVER}
    )
    if packet.failed_gate_ids != actual_failed:
        raise ValidationError("failed gate index does not match gate outcomes")
    if packet.blocked_gate_ids != actual_blocked:
        raise ValidationError("blocked gate index does not match gate outcomes")
    if packet.passed_gate_ids != actual_passed:
        raise ValidationError("passed gate index does not match gate outcomes")
    for gate in packet.gates:
        if gate.status is GateStatus.PASS_WITH_WAIVER and gate.waiver_id is None:
            raise ValidationError(f"waived gate has no waiver identifier: {gate.gate_id}")
        if gate.status is not GateStatus.PASS_WITH_WAIVER and gate.waiver_id is not None:
            raise ValidationError(f"non-waived gate carries a waiver identifier: {gate.gate_id}")

    if packet.failed_gate_ids and packet.decision is not DecisionStatus.FAIL:
        raise ValidationError("failed mandatory gate did not produce FAIL")
    if (
        not packet.failed_gate_ids
        and packet.blocked_gate_ids
        and packet.decision is not DecisionStatus.BLOCKED
    ):
        raise ValidationError("blocked mandatory gate did not produce BLOCKED")
    if (
        not packet.failed_gate_ids
        and not packet.blocked_gate_ids
        and packet.decision is not DecisionStatus.PASS
    ):
        raise ValidationError("fully satisfied gates did not produce PASS")
