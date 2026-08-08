from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from .domain import DecisionStatus, GatePolicy, WaiverPolicy
from .errors import ValidationError


@dataclass(frozen=True, slots=True)
class DecisionPolicy:
    policy_id: str
    policy_version: str
    decision_precedence: tuple[DecisionStatus, ...]
    gates: tuple[GatePolicy, ...]

    @property
    def gates_by_id(self) -> dict[str, GatePolicy]:
        return {gate.gate_id: gate for gate in self.gates}


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValidationError(f"{field} must be a non-empty string")
    return value


def load_policy(policy_dir: Path) -> DecisionPolicy:
    if policy_dir.is_symlink():
        raise ValidationError(f"policy directory may not be a symlink: {policy_dir}")
    path = policy_dir.resolve() / "gates.json"
    if path.is_symlink():
        raise ValidationError(f"policy file may not be a symlink: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"invalid policy file: {path}") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("gates"), list):
        raise ValidationError("policy must contain a gates list")
    precedence_raw = raw.get("decision_precedence")
    if precedence_raw != ["FAIL", "BLOCKED", "PASS"]:
        raise ValidationError("decision precedence must be FAIL > BLOCKED > PASS")
    gates: list[GatePolicy] = []
    seen: set[str] = set()
    for item_raw in cast(list[object], raw["gates"]):
        if not isinstance(item_raw, dict):
            raise ValidationError("gate policy must be an object")
        item = cast(Mapping[str, Any], item_raw)
        gate_id = _text(item.get("gate_id"), "gate_id")
        if gate_id in seen:
            raise ValidationError(f"duplicate gate: {gate_id}")
        if item.get("criticality") != "MANDATORY":
            raise ValidationError(f"all frozen-case gates must be mandatory: {gate_id}")
        if item.get("evidence_cardinality") != "EXACTLY_ONE":
            raise ValidationError(f"unsupported evidence cardinality: {gate_id}")
        try:
            gate = GatePolicy(
                gate_id=gate_id,
                title=_text(item.get("title"), f"{gate_id}.title"),
                domain=_text(item.get("domain"), f"{gate_id}.domain"),
                owner_role=_text(item.get("owner_role"), f"{gate_id}.owner_role"),
                criticality="MANDATORY",
                evidence_cardinality="EXACTLY_ONE",
                explicit_fail_effect=DecisionStatus(
                    _text(item.get("explicit_fail_effect"), "explicit_fail_effect")
                ),
                missing_effect=DecisionStatus(_text(item.get("missing_effect"), "missing_effect")),
                stale_effect=DecisionStatus(_text(item.get("stale_effect"), "stale_effect")),
                pending_approval_effect=DecisionStatus(
                    _text(item.get("pending_approval_effect"), "pending_approval_effect")
                ),
                waiver_policy=WaiverPolicy(_text(item.get("waiver_policy"), "waiver_policy")),
            )
        except ValueError as exc:
            raise ValidationError(f"invalid gate enumeration: {gate_id}") from exc
        if gate.explicit_fail_effect is not DecisionStatus.FAIL:
            raise ValidationError(f"explicit failure must produce FAIL: {gate_id}")
        if gate.missing_effect is not DecisionStatus.BLOCKED:
            raise ValidationError(f"missing evidence must produce BLOCKED: {gate_id}")
        if gate.stale_effect is not DecisionStatus.BLOCKED:
            raise ValidationError(f"stale evidence must produce BLOCKED: {gate_id}")
        if gate.pending_approval_effect is not DecisionStatus.BLOCKED:
            raise ValidationError(f"pending approval must produce BLOCKED: {gate_id}")
        seen.add(gate_id)
        gates.append(gate)
    expected_gate_ids = {f"G-{index:02d}" for index in range(1, 15)}
    if len(gates) != 14 or seen != expected_gate_ids:
        raise ValidationError(
            f"expected exact readiness gates G-01 through G-14, found {sorted(seen)}"
        )
    return DecisionPolicy(
        policy_id=_text(raw.get("policy_id"), "policy_id"),
        policy_version=_text(raw.get("policy_version"), "policy_version"),
        decision_precedence=(
            DecisionStatus.FAIL,
            DecisionStatus.BLOCKED,
            DecisionStatus.PASS,
        ),
        gates=tuple(gates),
    )
