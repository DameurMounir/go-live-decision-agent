#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from go_live_decision_agent.case_validation import validate_case

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    summary: dict[str, object] = {}
    for scenario in ("pass", "blocked", "fail"):
        case = validate_case(ROOT / "cases" / scenario)
        summary[scenario] = {
            "candidate_id": case.candidate["candidate_id"],
            "evidence_count": len(case.evidence),
            "waiver_count": len(case.waivers),
        }
    print(json.dumps(summary, indent=2, sort_keys=True))
    print("PASS: manifests, evidence digests, dates, identities, and case boundaries verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
