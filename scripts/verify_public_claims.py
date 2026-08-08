#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    required = [
        "| `pass` | 14 | 0 | 0 | **PASS** |",
        "| `blocked` | 11 | 3 | 0 | **BLOCKED** |",
        "| `fail` | 12 | 0 | 2 | **FAIL** |",
        "FAIL > BLOCKED > PASS",
        "Live model evaluation is `NOT_RUN`",
        "does **not** deploy",
    ]
    missing = [value for value in required if value not in readme]
    if missing:
        raise SystemExit(f"README claim contract missing: {missing}")
    evaluation = json.loads(
        (ROOT / "evaluation" / "results" / "evaluation.json").read_text(encoding="utf-8")
    )
    metrics = evaluation["evaluation"]
    if metrics["status"] != "PASS":
        raise SystemExit("public evaluation status is not PASS")
    if metrics["exact_decision_agreement"] != 1.0:
        raise SystemExit("public exact-agreement claim is not supported")
    if metrics["gate_traceability_rate"] != 1.0:
        raise SystemExit("public traceability claim is not supported")
    if metrics["zero_false_pass"] is not True:
        raise SystemExit("public zero-false-PASS claim is not supported")
    print("PASS: README decisions, metrics, and authority boundaries verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
