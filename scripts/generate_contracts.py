#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_ROOT = ROOT / "schemas"


def schemas() -> dict[str, dict[str, Any]]:
    decision = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://example.invalid/go-live-decision.schema.json",
        "additionalProperties": False,
        "properties": {
            "assessment_date": {"format": "date", "type": "string"},
            "authority_boundary": {"minLength": 1, "type": "string"},
            "blocked_gate_ids": {"items": {"type": "string"}, "type": "array"},
            "candidate_id": {"minLength": 1, "type": "string"},
            "candidate_version": {"minLength": 1, "type": "string"},
            "decision": {"enum": ["PASS", "BLOCKED", "FAIL"]},
            "decision_digest": {"pattern": "^[0-9a-f]{64}$", "type": "string"},
            "failed_gate_ids": {"items": {"type": "string"}, "type": "array"},
            "gates": {
                "items": {
                    "additionalProperties": False,
                    "properties": {
                        "domain": {"type": "string"},
                        "evidence_ids": {"items": {"type": "string"}, "type": "array"},
                        "gate_id": {"type": "string"},
                        "reason_codes": {"items": {"type": "string"}, "type": "array"},
                        "status": {"enum": ["PASS", "PASS_WITH_WAIVER", "BLOCKED", "FAIL"]},
                        "title": {"type": "string"},
                        "waiver_id": {"type": ["string", "null"]},
                    },
                    "required": [
                        "domain",
                        "evidence_ids",
                        "gate_id",
                        "reason_codes",
                        "status",
                        "title",
                        "waiver_id",
                    ],
                    "type": "object",
                },
                "type": "array",
            },
            "limitations": {"items": {"type": "string"}, "type": "array"},
            "passed_gate_ids": {"items": {"type": "string"}, "type": "array"},
            "policy_id": {"type": "string"},
            "policy_version": {"type": "string"},
            "required_actions": {"items": {"type": "string"}, "type": "array"},
            "residual_risks": {"items": {"type": "string"}, "type": "array"},
            "scenario": {"type": "string"},
        },
        "required": [
            "assessment_date",
            "authority_boundary",
            "blocked_gate_ids",
            "candidate_id",
            "candidate_version",
            "decision",
            "decision_digest",
            "failed_gate_ids",
            "gates",
            "limitations",
            "passed_gate_ids",
            "policy_id",
            "policy_version",
            "required_actions",
            "residual_risks",
            "scenario",
        ],
        "title": "Go-Live Decision Packet",
        "type": "object",
    }
    review = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://example.invalid/go-live-review.schema.json",
        "additionalProperties": False,
        "properties": {
            "action": {"enum": ["CONFIRM", "REQUEST_REVISION", "REJECT"]},
            "comment": {"maxLength": 2000, "type": "string"},
            "decision_digest": {"pattern": "^[0-9a-f]{64}$", "type": "string"},
            "nonce": {"minLength": 32, "type": "string"},
            "reviewer": {"minLength": 1, "type": "string"},
            "run_id": {"minLength": 1, "type": "string"},
        },
        "required": ["action", "decision_digest", "nonce", "reviewer", "run_id"],
        "title": "Go-Live Human Review Command",
        "type": "object",
    }
    return {"decision-packet.schema.json": decision, "review-command.schema.json": review}


def write_into(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for name, value in schemas().items():
        (root / name).write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


def tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*.json"))
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        with tempfile.TemporaryDirectory() as tmp:
            generated = Path(tmp)
            write_into(generated)
            if tree(generated) != tree(SCHEMA_ROOT):
                raise SystemExit("generated JSON schemas differ from committed schemas")
        print("PASS: generated decision and review schemas are byte-stable")
        return 0
    shutil.rmtree(SCHEMA_ROOT, ignore_errors=True)
    write_into(SCHEMA_ROOT)
    print("PASS: generated decision and review schemas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
