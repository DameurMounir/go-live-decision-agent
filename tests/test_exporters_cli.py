from __future__ import annotations

import json
from pathlib import Path

from go_live_decision_agent.cli import main
from go_live_decision_agent.domain import ReviewAction
from go_live_decision_agent.exporters import verify_export_equivalence, write_exports
from go_live_decision_agent.service import GoLiveDecisionService
from go_live_decision_agent.store import ReviewStore

ROOT = Path(__file__).resolve().parents[1]


def test_exports_are_equivalent_and_safe(tmp_path: Path) -> None:
    store = ReviewStore(tmp_path / "review.sqlite3")
    packet = GoLiveDecisionService(ROOT / "policy").decide(ROOT / "cases" / "blocked")[0]
    store.create_run("RUN-001", packet)
    challenge = store.issue_challenge(
        "RUN-001",
        packet.decision_digest,
        nonce_factory=lambda: "x" * 32,
    )
    store.record_review(
        run_id="RUN-001",
        decision_digest=packet.decision_digest,
        nonce=challenge.nonce,
        reviewer="<Release Authority>",
        action=ReviewAction.CONFIRM,
        comment="<script>alert('x')</script>",
    )
    paths = write_exports(store, "RUN-001", tmp_path / "exports")
    assert verify_export_equivalence(paths["json"], paths["markdown"], paths["html"])
    html = paths["html"].read_text()
    assert "<script>alert" not in html
    assert "&lt;Release Authority&gt;" in html


def test_tampered_markdown_export_is_rejected(tmp_path: Path) -> None:
    store = ReviewStore(tmp_path / "review.sqlite3")
    packet = GoLiveDecisionService(ROOT / "policy").decide(ROOT / "cases" / "pass")[0]
    store.create_run("RUN-001", packet)
    paths = write_exports(store, "RUN-001", tmp_path / "exports")
    paths["markdown"].write_text("<!-- decision-snapshot-sha256:" + "0" * 64 + " -->\n")
    from go_live_decision_agent.errors import ValidationError

    try:
        verify_export_equivalence(paths["json"], paths["markdown"], paths["html"])
    except ValidationError:
        pass
    else:
        raise AssertionError("tampered export should be rejected")


def test_cli_complete_workflow(tmp_path: Path, capsys) -> None:
    decision = tmp_path / "decision.json"
    database = tmp_path / "review.sqlite3"
    assert (
        main(
            [
                "decide",
                "--case",
                str(ROOT / "cases" / "blocked"),
                "--policy",
                str(ROOT / "policy"),
                "--output",
                str(decision),
                "--db",
                str(database),
                "--run-id",
                "RUN-CLI-001",
            ]
        )
        == 0
    )
    payload = json.loads(decision.read_text())
    digest = payload["packet"]["decision_digest"]
    assert (
        main(
            [
                "review-init",
                "--db",
                str(database),
                "--run-id",
                "RUN-CLI-001",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    challenge = json.loads(output[output.rfind("{\n") :])
    assert (
        main(
            [
                "review",
                "--db",
                str(database),
                "--run-id",
                "RUN-CLI-001",
                "--decision-digest",
                digest,
                "--nonce",
                challenge["nonce"],
                "--reviewer",
                "Release Authority",
                "--action",
                "CONFIRM",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "export",
                "--db",
                str(database),
                "--run-id",
                "RUN-CLI-001",
                "--output-dir",
                str(tmp_path / "exports"),
            ]
        )
        == 0
    )
    assert main(["verify-ledger", "--db", str(database)]) == 0


def test_cli_rejects_invalid_run_identifier(tmp_path: Path) -> None:
    decision = tmp_path / "decision.json"
    assert (
        main(
            [
                "decide",
                "--case",
                str(ROOT / "cases" / "pass"),
                "--policy",
                str(ROOT / "policy"),
                "--output",
                str(decision),
                "--db",
                str(tmp_path / "review.sqlite3"),
                "--run-id",
                "../escape",
            ]
        )
        == 2
    )
