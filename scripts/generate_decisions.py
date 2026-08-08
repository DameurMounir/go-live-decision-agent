#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from go_live_decision_agent.service import GoLiveDecisionService

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = ROOT / "expected"


def write_into(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    service = GoLiveDecisionService(ROOT / "policy")
    for scenario in ("pass", "blocked", "fail"):
        packet, note = service.decide(ROOT / "cases" / scenario)
        payload = {
            "advisory": {
                "adapter_id": note.adapter_id,
                "authority": note.authority,
                "decision": note.decision.value,
                "decision_digest": note.decision_digest,
                "summary": note.summary,
            },
            "packet": packet.as_dict(),
        }
        (root / f"{scenario}-decision.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
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
            if tree(generated) != tree(EXPECTED):
                raise SystemExit("generated decision packets differ from committed packets")
        print("PASS: frozen PASS/BLOCKED/FAIL decision packets are byte-stable")
        return 0
    shutil.rmtree(EXPECTED, ignore_errors=True)
    write_into(EXPECTED)
    print("PASS: generated frozen decision packets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
