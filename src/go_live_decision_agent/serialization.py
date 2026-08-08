from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from .domain import DecisionPacket, DecisionStatus, GateOutcome, GateStatus


def packet_from_dict(value: Mapping[str, Any]) -> DecisionPacket:
    gates_raw = value.get("gates")
    if not isinstance(gates_raw, list):
        raise ValueError("packet gates must be a list")
    gates = tuple(
        GateOutcome(
            gate_id=str(item["gate_id"]),
            title=str(item["title"]),
            domain=str(item["domain"]),
            status=GateStatus(str(item["status"])),
            reason_codes=tuple(str(v) for v in cast(list[object], item["reason_codes"])),
            evidence_ids=tuple(str(v) for v in cast(list[object], item["evidence_ids"])),
            waiver_id=None if item.get("waiver_id") is None else str(item["waiver_id"]),
        )
        for item in cast(list[dict[str, Any]], gates_raw)
    )
    return DecisionPacket(
        candidate_id=str(value["candidate_id"]),
        candidate_version=str(value["candidate_version"]),
        scenario=str(value["scenario"]),
        assessment_date=str(value["assessment_date"]),
        policy_id=str(value["policy_id"]),
        policy_version=str(value["policy_version"]),
        decision=DecisionStatus(str(value["decision"])),
        gates=gates,
        failed_gate_ids=tuple(str(v) for v in cast(list[object], value["failed_gate_ids"])),
        blocked_gate_ids=tuple(str(v) for v in cast(list[object], value["blocked_gate_ids"])),
        passed_gate_ids=tuple(str(v) for v in cast(list[object], value["passed_gate_ids"])),
        residual_risks=tuple(str(v) for v in cast(list[object], value["residual_risks"])),
        required_actions=tuple(str(v) for v in cast(list[object], value["required_actions"])),
        limitations=tuple(str(v) for v in cast(list[object], value["limitations"])),
        authority_boundary=str(value["authority_boundary"]),
        decision_digest=str(value["decision_digest"]),
    )
