"""Command-line interface for the local go-live decision workflow."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from .canonical import pretty_json
from .case_validation import validate_case
from .domain import ReviewAction
from .errors import GoLiveDecisionError
from .exporters import verify_export_equivalence, write_exports
from .paths import packaged_cases_dir, packaged_policy_dir, validate_identifier
from .service import GoLiveDecisionService
from .store import ReviewStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="go-live-decision-agent",
        description="Evidence-bound PASS, BLOCKED, or FAIL readiness decisions.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="validate a case and policy")
    validate.add_argument("--case", type=Path, required=True)
    validate.add_argument("--policy", type=Path, default=packaged_policy_dir())

    decide = sub.add_parser("decide", help="compute a deterministic decision packet")
    decide.add_argument("--case", type=Path, required=True)
    decide.add_argument("--policy", type=Path, default=packaged_policy_dir())
    decide.add_argument("--output", type=Path, required=True)
    decide.add_argument("--db", type=Path)
    decide.add_argument("--run-id")

    review_init = sub.add_parser("review-init", help="issue a digest-bound review challenge")
    review_init.add_argument("--db", type=Path, required=True)
    review_init.add_argument("--run-id", required=True)
    review_init.add_argument("--ttl-seconds", type=int, default=600)

    review = sub.add_parser("review", help="record one human review")
    review.add_argument("--db", type=Path, required=True)
    review.add_argument("--run-id", required=True)
    review.add_argument("--decision-digest", required=True)
    review.add_argument("--nonce", required=True)
    review.add_argument("--reviewer", required=True)
    review.add_argument("--action", choices=[item.value for item in ReviewAction], required=True)
    review.add_argument("--comment", default="")

    export = sub.add_parser("export", help="export equivalent JSON, Markdown, and HTML")
    export.add_argument("--db", type=Path, required=True)
    export.add_argument("--run-id", required=True)
    export.add_argument("--output-dir", type=Path, required=True)

    verify_ledger = sub.add_parser("verify-ledger", help="verify hash-linked review events")
    verify_ledger.add_argument("--db", type=Path, required=True)

    demo = sub.add_parser("demo", help="run all frozen sample decisions")
    demo.add_argument("--output-dir", type=Path, required=True)
    return parser


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(pretty_json(value), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        if args.command == "validate":
            case = validate_case(args.case)
            service = GoLiveDecisionService(args.policy)
            packet, _ = service.decide(args.case)
            print(
                pretty_json(
                    {
                        "candidate_id": case.candidate["candidate_id"],
                        "decision": packet.decision.value,
                        "decision_digest": packet.decision_digest,
                    }
                ),
                end="",
            )
            return 0
        if args.command == "decide":
            packet, note = GoLiveDecisionService(args.policy).decide(args.case)
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
            _write_json(args.output, payload)
            if args.db is not None:
                if not args.run_id:
                    raise GoLiveDecisionError("--run-id is required when --db is used")
                run_id = validate_identifier(str(args.run_id), field="run_id")
                ReviewStore(args.db).create_run(run_id, packet)
            print(
                pretty_json(
                    {"decision": packet.decision.value, "decision_digest": packet.decision_digest}
                ),
                end="",
            )
            return 0
        if args.command == "review-init":
            run_id = validate_identifier(args.run_id, field="run_id")
            store = ReviewStore(args.db)
            packet = store.load_packet(run_id)
            print(
                pretty_json(
                    store.issue_challenge(
                        run_id,
                        packet.decision_digest,
                        ttl_seconds=args.ttl_seconds,
                    ).as_dict()
                ),
                end="",
            )
            return 0
        if args.command == "review":
            run_id = validate_identifier(args.run_id, field="run_id")
            record = ReviewStore(args.db).record_review(
                run_id=run_id,
                decision_digest=args.decision_digest,
                nonce=args.nonce,
                reviewer=args.reviewer,
                action=ReviewAction(args.action),
                comment=args.comment,
            )
            print(pretty_json(record.as_dict()), end="")
            return 0
        if args.command == "export":
            run_id = validate_identifier(args.run_id, field="run_id")
            paths = write_exports(ReviewStore(args.db), run_id, args.output_dir)
            digest = verify_export_equivalence(paths["json"], paths["markdown"], paths["html"])
            print(
                pretty_json(
                    {"paths": {k: str(v) for k, v in paths.items()}, "snapshot_sha256": digest}
                ),
                end="",
            )
            return 0
        if args.command == "verify-ledger":
            ReviewStore(args.db).verify_ledger()
            print("PASS: review ledger is hash-linked and internally consistent")
            return 0
        if args.command == "demo":
            args.output_dir.mkdir(parents=True, exist_ok=True)
            service = GoLiveDecisionService(packaged_policy_dir())
            result: dict[str, object] = {}
            for scenario in ("pass", "blocked", "fail"):
                packet, note = service.decide(packaged_cases_dir() / scenario)
                result[scenario] = {
                    "advisory": note.summary,
                    "decision": packet.decision.value,
                    "decision_digest": packet.decision_digest,
                }
            _write_json(args.output_dir / "demo-decisions.json", result)
            print(pretty_json(result), end="")
            return 0
        raise AssertionError(f"unhandled command: {args.command}")
    except GoLiveDecisionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
