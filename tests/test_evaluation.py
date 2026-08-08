from pathlib import Path

from scripts.evaluate import adversarial_decisions, evaluate_repository

ROOT = Path(__file__).resolve().parents[1]


def test_evaluation_passes() -> None:
    result = evaluate_repository(ROOT)
    assert result.status == "PASS"
    assert result.exact_decision_agreement == 1.0
    assert result.zero_false_pass is True
    assert result.gate_traceability_rate == 1.0
    assert result.runtime_answer_key_isolation is True


def test_adversarial_decisions_never_false_pass() -> None:
    assert adversarial_decisions(ROOT) == {
        "explicit_failure": "FAIL",
        "missing_evidence": "BLOCKED",
        "stale_or_pending_evidence": "BLOCKED",
    }
