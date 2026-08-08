#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CASES_ROOT = ROOT / "cases"
EVALUATION_ROOT = ROOT / "evaluation"
SCHEMA_VERSION = "1.0.0"
ASSESSMENT_DATE = "2026-08-01"
CANDIDATE_ID = "ATLASBRIDGE-ONBOARDING-2"
CANDIDATE_VERSION = "2.0.0-rc.4"

GATES = [
    ("G-01", "Release identity and scope", "Release Manager"),
    ("G-02", "Business acceptance", "Business Owner"),
    ("G-03", "Functional acceptance", "QA Lead"),
    ("G-04", "Security verification", "Security Lead"),
    ("G-05", "Privacy and data protection", "Privacy Lead"),
    ("G-06", "Data migration and reconciliation", "Data Lead"),
    ("G-07", "Performance and capacity", "Performance Lead"),
    ("G-08", "Reliability and recovery", "SRE Lead"),
    ("G-09", "Observability and incident response", "Operations Lead"),
    ("G-10", "Support readiness", "Support Lead"),
    ("G-11", "Training and communications", "Change Lead"),
    ("G-12", "Rollback and rollforward readiness", "Release Engineering Lead"),
    ("G-13", "External dependency readiness", "Vendor Manager"),
    ("G-14", "Release authority and window", "Release Authority"),
]


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def evidence(
    gate_id: str,
    title: str,
    owner: str,
    *,
    status: str = "PASS",
    observed_at: str = "2026-07-25",
    expires_at: str = "2026-08-15",
    approval_state: str = "APPROVED",
    assertion: str | None = None,
) -> dict[str, Any]:
    payload = {
        "approval_state": approval_state,
        "assertion": assertion
        or f"{title} evidence satisfies the frozen synthetic release criterion.",
        "candidate_id": CANDIDATE_ID,
        "candidate_version": CANDIDATE_VERSION,
        "evidence_id": f"E-{gate_id[2:]}",
        "expires_at": expires_at,
        "gate_id": gate_id,
        "issuer": owner,
        "observed_at": observed_at,
        "owner": owner,
        "schema_version": SCHEMA_VERSION,
        "source_type": "SYNTHETIC_ATTESTATION",
        "status": status,
        "title": f"{title} evidence",
    }
    payload["payload_sha256"] = digest(payload)
    return payload


def case_payload(
    scenario: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    candidate = {
        "assessment_date": ASSESSMENT_DATE,
        "candidate_id": CANDIDATE_ID,
        "candidate_version": CANDIDATE_VERSION,
        "change_summary": "Controlled onboarding workflow with reusable intake, parallel checks, evidence-bound activation, and operational guardrails.",
        "data_classification": "SYNTHETIC_PUBLIC",
        "decision_question": "Is there enough evidence to proceed: PASS, BLOCKED, or FAIL?",
        "release_window": "2026-08-10T22:00:00Z/2026-08-11T01:00:00Z",
        "scenario": scenario,
        "schema_version": SCHEMA_VERSION,
    }
    items = [evidence(*gate) for gate in GATES]
    waivers: list[dict[str, Any]] = []
    if scenario == "blocked":
        items = [item for item in items if item["gate_id"] != "G-13"]
        for item in items:
            if item["gate_id"] == "G-11":
                stale = {**item, "expires_at": "2026-07-31"}
                stale.pop("payload_sha256")
                stale["payload_sha256"] = digest(stale)
                item.clear()
                item.update(stale)
            elif item["gate_id"] == "G-14":
                pending = {**item, "approval_state": "PENDING"}
                pending.pop("payload_sha256")
                pending["payload_sha256"] = digest(pending)
                item.clear()
                item.update(pending)
    elif scenario == "fail":
        for item in items:
            if item["gate_id"] == "G-04":
                failed = {
                    **item,
                    "assertion": "A synthetic critical security defect remains open and blocks release.",
                    "status": "FAIL",
                }
                failed.pop("payload_sha256")
                failed["payload_sha256"] = digest(failed)
                item.clear()
                item.update(failed)
            elif item["gate_id"] == "G-12":
                failed = {
                    **item,
                    "assertion": "The synthetic rollback rehearsal exceeded the recovery boundary and did not restore service.",
                    "status": "FAIL",
                }
                failed.pop("payload_sha256")
                failed["payload_sha256"] = digest(failed)
                item.clear()
                item.update(failed)
    elif scenario != "pass":
        raise ValueError(f"unknown scenario: {scenario}")
    return candidate, items, waivers


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_into(target_root: Path) -> None:
    for scenario in ("pass", "blocked", "fail"):
        case_dir = target_root / scenario
        candidate, items, waivers = case_payload(scenario)
        write_json(case_dir / "candidate.json", candidate)
        write_json(
            case_dir / "evidence.json", {"evidence": items, "schema_version": SCHEMA_VERSION}
        )
        write_json(
            case_dir / "waivers.json", {"schema_version": SCHEMA_VERSION, "waivers": waivers}
        )
        manifest_files = []
        for path in sorted(case_dir.glob("*.json")):
            if path.name == "manifest.json":
                continue
            manifest_files.append(
                {
                    "bytes": path.stat().st_size,
                    "path": path.name,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
        write_json(
            case_dir / "manifest.json",
            {
                "case_id": f"GLD-{scenario.upper()}-001",
                "files": manifest_files,
                "scenario": scenario,
                "schema_version": SCHEMA_VERSION,
            },
        )
    write_json(
        EVALUATION_ROOT / "answer-key.json",
        {
            "answer_key_policy": "Evaluation-only. Runtime decision code must not read this file.",
            "cases": {
                "blocked": {
                    "blocked_gate_ids": ["G-11", "G-13", "G-14"],
                    "decision": "BLOCKED",
                    "failed_gate_ids": [],
                },
                "fail": {
                    "blocked_gate_ids": [],
                    "decision": "FAIL",
                    "failed_gate_ids": ["G-04", "G-12"],
                },
                "pass": {
                    "blocked_gate_ids": [],
                    "decision": "PASS",
                    "failed_gate_ids": [],
                },
            },
            "schema_version": SCHEMA_VERSION,
        },
    )


def directory_digest(root: Path) -> dict[str, bytes]:
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
            generated_cases = Path(tmp) / "cases"
            evaluation_backup = EVALUATION_ROOT / "answer-key.json"
            existing_answer = evaluation_backup.read_bytes() if evaluation_backup.exists() else None
            build_into(generated_cases)
            generated = directory_digest(generated_cases)
            committed = directory_digest(CASES_ROOT)
            if existing_answer is not None:
                evaluation_backup.write_bytes(existing_answer)
            if generated != committed:
                raise SystemExit("generated cases differ from committed cases")
        print("PASS: frozen PASS/BLOCKED/FAIL cases are byte-stable")
        return 0
    shutil.rmtree(CASES_ROOT, ignore_errors=True)
    build_into(CASES_ROOT)
    print(f"PASS: wrote frozen cases to {CASES_ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
