from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from go_live_decision_agent.domain import DecisionStatus, GateStatus, WaiverPolicy
from go_live_decision_agent.errors import ValidationError
from go_live_decision_agent.policy import load_policy

ROOT = Path(__file__).resolve().parents[1]


def test_policy_loads_fourteen_mandatory_gates() -> None:
    policy = load_policy(ROOT / "policy")
    assert len(policy.gates) == 14
    assert policy.decision_precedence == (
        DecisionStatus.FAIL,
        DecisionStatus.BLOCKED,
        DecisionStatus.PASS,
    )


def test_gate_identifiers_are_unique() -> None:
    policy = load_policy(ROOT / "policy")
    assert len(policy.gates_by_id) == 14


@pytest.mark.parametrize("gate_id", ["G-11", "G-13"])
def test_bounded_gates_are_waivable(gate_id: str) -> None:
    assert load_policy(ROOT / "policy").gates_by_id[gate_id].waiver_policy is WaiverPolicy.WAIVABLE


@pytest.mark.parametrize("gate_id", ["G-01", "G-04", "G-06", "G-12", "G-14"])
def test_critical_gates_are_non_waivable(gate_id: str) -> None:
    assert (
        load_policy(ROOT / "policy").gates_by_id[gate_id].waiver_policy is WaiverPolicy.NON_WAIVABLE
    )


def test_gate_status_enumeration_is_explicit() -> None:
    assert {item.value for item in GateStatus} == {
        "PASS",
        "PASS_WITH_WAIVER",
        "BLOCKED",
        "FAIL",
    }


def _copy_policy(tmp_path: Path) -> Path:
    target = tmp_path / "policy"
    shutil.copytree(ROOT / "policy", target)
    return target


def test_changed_precedence_is_rejected(tmp_path: Path) -> None:
    target = _copy_policy(tmp_path)
    path = target / "gates.json"
    payload = json.loads(path.read_text())
    payload["decision_precedence"] = ["BLOCKED", "FAIL", "PASS"]
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    with pytest.raises(ValidationError, match="precedence"):
        load_policy(target)


def test_missing_gate_is_rejected(tmp_path: Path) -> None:
    target = _copy_policy(tmp_path)
    path = target / "gates.json"
    payload = json.loads(path.read_text())
    payload["gates"].pop()
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    with pytest.raises(ValidationError, match="14"):
        load_policy(target)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("explicit_fail_effect", "BLOCKED", "explicit failure"),
        ("missing_effect", "PASS", "missing evidence"),
        ("stale_effect", "PASS", "stale evidence"),
        ("pending_approval_effect", "PASS", "pending approval"),
    ],
)
def test_unsafe_gate_effect_is_rejected(
    tmp_path: Path,
    field: str,
    value: str,
    message: str,
) -> None:
    target = _copy_policy(tmp_path)
    path = target / "gates.json"
    payload = json.loads(path.read_text())
    payload["gates"][0][field] = value
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    with pytest.raises(ValidationError, match=message):
        load_policy(target)
