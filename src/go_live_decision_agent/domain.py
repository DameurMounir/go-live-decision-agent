from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class DecisionStatus(StrEnum):
    PASS = "PASS"
    BLOCKED = "BLOCKED"
    FAIL = "FAIL"


class GateStatus(StrEnum):
    PASS = "PASS"
    PASS_WITH_WAIVER = "PASS_WITH_WAIVER"
    BLOCKED = "BLOCKED"
    FAIL = "FAIL"


class EvidenceStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"


class ApprovalState(StrEnum):
    APPROVED = "APPROVED"
    PENDING = "PENDING"
    REJECTED = "REJECTED"


class WaiverPolicy(StrEnum):
    WAIVABLE = "WAIVABLE"
    NON_WAIVABLE = "NON_WAIVABLE"


class ReviewAction(StrEnum):
    CONFIRM = "CONFIRM"
    REQUEST_REVISION = "REQUEST_REVISION"
    REJECT = "REJECT"


class ReviewState(StrEnum):
    UNREVIEWED = "UNREVIEWED"
    CONFIRMED = "CONFIRMED"
    REVISION_REQUESTED = "REVISION_REQUESTED"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class GatePolicy:
    gate_id: str
    title: str
    domain: str
    owner_role: str
    criticality: str
    evidence_cardinality: str
    explicit_fail_effect: DecisionStatus
    missing_effect: DecisionStatus
    stale_effect: DecisionStatus
    pending_approval_effect: DecisionStatus
    waiver_policy: WaiverPolicy


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    evidence_id: str
    gate_id: str
    title: str
    status: EvidenceStatus
    approval_state: ApprovalState
    observed_at: str
    expires_at: str
    owner: str
    issuer: str
    candidate_id: str
    candidate_version: str
    assertion: str
    source_type: str
    payload_sha256: str


@dataclass(frozen=True, slots=True)
class Waiver:
    waiver_id: str
    gate_id: str
    candidate_id: str
    candidate_version: str
    authority: str
    rationale: str
    approved_at: str
    expires_at: str
    status: str
    payload_sha256: str


@dataclass(frozen=True, slots=True)
class GateOutcome:
    gate_id: str
    title: str
    domain: str
    status: GateStatus
    reason_codes: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    waiver_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "evidence_ids": list(self.evidence_ids),
            "gate_id": self.gate_id,
            "reason_codes": list(self.reason_codes),
            "status": self.status.value,
            "title": self.title,
            "waiver_id": self.waiver_id,
        }


@dataclass(frozen=True, slots=True)
class DecisionPacket:
    candidate_id: str
    candidate_version: str
    scenario: str
    assessment_date: str
    policy_id: str
    policy_version: str
    decision: DecisionStatus
    gates: tuple[GateOutcome, ...]
    failed_gate_ids: tuple[str, ...]
    blocked_gate_ids: tuple[str, ...]
    passed_gate_ids: tuple[str, ...]
    residual_risks: tuple[str, ...]
    required_actions: tuple[str, ...]
    limitations: tuple[str, ...]
    authority_boundary: str
    decision_digest: str = field(default="")

    def as_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        value: dict[str, Any] = {
            "assessment_date": self.assessment_date,
            "authority_boundary": self.authority_boundary,
            "blocked_gate_ids": list(self.blocked_gate_ids),
            "candidate_id": self.candidate_id,
            "candidate_version": self.candidate_version,
            "decision": self.decision.value,
            "failed_gate_ids": list(self.failed_gate_ids),
            "gates": [gate.as_dict() for gate in self.gates],
            "limitations": list(self.limitations),
            "passed_gate_ids": list(self.passed_gate_ids),
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "required_actions": list(self.required_actions),
            "residual_risks": list(self.residual_risks),
            "scenario": self.scenario,
        }
        if include_digest:
            value["decision_digest"] = self.decision_digest
        return value


def string_tuple(value: Sequence[object], field_name: str) -> tuple[str, ...]:
    if not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{field_name} must contain non-empty strings")
    return tuple(str(item) for item in value)


def require_mapping(value: object, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping")
    return value
