#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from go_live_decision_agent.case_validation import ValidatedCase, validate_case
from go_live_decision_agent.domain import DecisionStatus
from go_live_decision_agent.engine import evaluate_case
from go_live_decision_agent.policy import load_policy
from go_live_decision_agent.service import GoLiveDecisionService

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evaluation" / "results"


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    scenario_agreement: Mapping[str, bool]
    exact_decision_agreement: float
    zero_false_pass: bool
    gate_traceability_rate: float
    runtime_answer_key_isolation: bool
    status: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "exact_decision_agreement": self.exact_decision_agreement,
            "gate_traceability_rate": self.gate_traceability_rate,
            "runtime_answer_key_isolation": self.runtime_answer_key_isolation,
            "scenario_agreement": dict(self.scenario_agreement),
            "status": self.status,
            "zero_false_pass": self.zero_false_pass,
        }


def _runtime_isolated(root: Path) -> bool:
    for path in (root / "src").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "answer-key.json" in text or "evaluation/answer-key" in text:
            return False
    return True


def evaluate_repository(root: Path) -> EvaluationResult:
    answer_path = root / "evaluation" / "answer-key.json"
    raw = json.loads(answer_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("cases"), dict):
        raise ValueError("evaluation answer key is invalid")
    cases = cast(dict[str, dict[str, Any]], raw["cases"])
    service = GoLiveDecisionService(root / "policy")
    agreement: dict[str, bool] = {}
    zero_false_pass = True
    traced = 0
    total_gates = 0
    for scenario, expected in sorted(cases.items()):
        packet, _ = service.decide(root / "cases" / scenario)
        agreement[scenario] = (
            packet.decision.value == expected["decision"]
            and list(packet.failed_gate_ids) == expected["failed_gate_ids"]
            and list(packet.blocked_gate_ids) == expected["blocked_gate_ids"]
        )
        if expected["decision"] != "PASS" and packet.decision is DecisionStatus.PASS:
            zero_false_pass = False
        total_gates += len(packet.gates)
        traced += sum(
            1
            for gate in packet.gates
            if gate.reason_codes
            and (gate.evidence_ids or "MISSING_REQUIRED_EVIDENCE" in gate.reason_codes)
        )
    exact = sum(agreement.values()) / len(agreement)
    traceability = traced / total_gates
    isolated = _runtime_isolated(root)
    status = (
        "PASS" if exact == 1.0 and zero_false_pass and traceability == 1.0 and isolated else "FAIL"
    )
    return EvaluationResult(
        scenario_agreement=agreement,
        exact_decision_agreement=exact,
        zero_false_pass=zero_false_pass,
        gate_traceability_rate=traceability,
        runtime_answer_key_isolation=isolated,
        status=status,
    )


def adversarial_decisions(root: Path) -> dict[str, str]:
    policy = load_policy(root / "policy")
    pass_case = validate_case(root / "cases" / "pass")
    blocked_case = validate_case(root / "cases" / "blocked")
    fail_case = validate_case(root / "cases" / "fail")

    missing = ValidatedCase(
        pass_case.case_dir,
        pass_case.candidate,
        tuple(item for item in pass_case.evidence if item["gate_id"] != "G-01"),
        pass_case.waivers,
    )
    stale = ValidatedCase(
        blocked_case.case_dir,
        blocked_case.candidate,
        blocked_case.evidence,
        blocked_case.waivers,
    )
    explicit_fail = ValidatedCase(
        fail_case.case_dir,
        fail_case.candidate,
        fail_case.evidence,
        fail_case.waivers,
    )
    return {
        "explicit_failure": evaluate_case(explicit_fail, policy).decision.value,
        "missing_evidence": evaluate_case(missing, policy).decision.value,
        "stale_or_pending_evidence": evaluate_case(stale, policy).decision.value,
    }


def payload() -> dict[str, Any]:
    result = evaluate_repository(ROOT)
    return {
        "adversarial_decisions": adversarial_decisions(ROOT),
        "claims": {
            "frozen_case_only": True,
            "live_model_evaluation": "NOT_RUN",
            "production_forecast": False,
            "release_authority": False,
        },
        "evaluation": result.as_dict(),
    }


def write_into(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    value = payload()
    (root / "evaluation.json").write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# Deterministic evaluation",
        "",
        f"- Status: **{value['evaluation']['status']}**",
        f"- Exact frozen-scenario agreement: {value['evaluation']['exact_decision_agreement']:.2%}",
        f"- Gate reason/evidence traceability: {value['evaluation']['gate_traceability_rate']:.2%}",
        f"- Zero false PASS in frozen adversarial scenarios: {value['evaluation']['zero_false_pass']}",
        f"- Runtime answer-key isolation: {value['evaluation']['runtime_answer_key_isolation']}",
        "",
        "These measurements prove agreement with one committed synthetic contract, not universal release-readiness accuracy.",
        "",
    ]
    (root / "evaluation.md").write_text("\n".join(lines), encoding="utf-8")


def tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        with tempfile.TemporaryDirectory() as tmp:
            generated = Path(tmp)
            write_into(generated)
            if tree(generated) != tree(RESULTS):
                raise SystemExit("evaluation results differ from committed results")
        print("PASS: deterministic evaluation results are byte-stable")
        return 0
    shutil.rmtree(RESULTS, ignore_errors=True)
    write_into(RESULTS)
    if payload()["evaluation"]["status"] != "PASS":
        raise SystemExit("deterministic evaluation failed")
    print("PASS: generated deterministic evaluation results")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
