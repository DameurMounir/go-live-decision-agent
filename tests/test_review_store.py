from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from go_live_decision_agent.domain import ReviewAction, ReviewState
from go_live_decision_agent.errors import (
    ReviewConflictError,
    SecurityBoundaryError,
    ValidationError,
)
from go_live_decision_agent.service import GoLiveDecisionService
from go_live_decision_agent.store import ReviewStore

ROOT = Path(__file__).resolve().parents[1]


def packet():
    return GoLiveDecisionService(ROOT / "policy").decide(ROOT / "cases" / "blocked")[0]


def test_run_challenge_review_and_ledger(tmp_path: Path) -> None:
    store = ReviewStore(tmp_path / "review.sqlite3")
    result = packet()
    store.create_run("RUN-001", result)
    challenge = store.issue_challenge(
        "RUN-001",
        result.decision_digest,
        nonce_factory=lambda: "n" * 32,
    )
    record = store.record_review(
        run_id="RUN-001",
        decision_digest=result.decision_digest,
        nonce=challenge.nonce,
        reviewer="Release Authority",
        action=ReviewAction.CONFIRM,
        comment="Confirmed as a synthetic decision packet.",
    )
    assert record.state is ReviewState.CONFIRMED
    store.verify_ledger()
    assert store.snapshot("RUN-001")["review_state"] == "CONFIRMED"


def test_stale_digest_is_rejected(tmp_path: Path) -> None:
    store = ReviewStore(tmp_path / "review.sqlite3")
    result = packet()
    store.create_run("RUN-001", result)
    with pytest.raises(ReviewConflictError, match="digest"):
        store.issue_challenge("RUN-001", "0" * 64)


def test_nonce_replay_is_rejected(tmp_path: Path) -> None:
    store = ReviewStore(tmp_path / "review.sqlite3")
    result = packet()
    store.create_run("RUN-001", result)
    challenge = store.issue_challenge(
        "RUN-001",
        result.decision_digest,
        nonce_factory=lambda: "r" * 32,
    )
    kwargs = {
        "run_id": "RUN-001",
        "decision_digest": result.decision_digest,
        "nonce": challenge.nonce,
        "reviewer": "Release Authority",
        "action": ReviewAction.CONFIRM,
    }
    store.record_review(**kwargs)
    with pytest.raises(ReviewConflictError, match="final human review"):
        store.record_review(**kwargs)


def test_superseded_challenge_is_rejected(tmp_path: Path) -> None:
    store = ReviewStore(tmp_path / "review.sqlite3")
    result = packet()
    store.create_run("RUN-001", result)
    first = store.issue_challenge(
        "RUN-001",
        result.decision_digest,
        nonce_factory=lambda: "a" * 32,
    )
    second = store.issue_challenge(
        "RUN-001",
        result.decision_digest,
        nonce_factory=lambda: "b" * 32,
    )
    with pytest.raises(ReviewConflictError, match="superseded"):
        store.record_review(
            run_id="RUN-001",
            decision_digest=result.decision_digest,
            nonce=first.nonce,
            reviewer="Release Authority",
            action=ReviewAction.REJECT,
        )
    assert (
        store.record_review(
            run_id="RUN-001",
            decision_digest=result.decision_digest,
            nonce=second.nonce,
            reviewer="Release Authority",
            action=ReviewAction.REQUEST_REVISION,
        ).state
        is ReviewState.REVISION_REQUESTED
    )


def test_expired_challenge_is_rejected(tmp_path: Path) -> None:
    now = datetime(2026, 8, 1, tzinfo=UTC)
    current = [now]
    store = ReviewStore(tmp_path / "review.sqlite3", clock=lambda: current[0])
    result = packet()
    store.create_run("RUN-001", result)
    challenge = store.issue_challenge(
        "RUN-001",
        result.decision_digest,
        ttl_seconds=60,
        nonce_factory=lambda: "e" * 32,
    )
    current[0] = now + timedelta(seconds=61)
    with pytest.raises(ReviewConflictError, match="expired"):
        store.record_review(
            run_id="RUN-001",
            decision_digest=result.decision_digest,
            nonce=challenge.nonce,
            reviewer="Release Authority",
            action=ReviewAction.REJECT,
        )


@pytest.mark.parametrize("ttl", [0, 59, 3601])
def test_invalid_ttl_is_rejected(tmp_path: Path, ttl: int) -> None:
    store = ReviewStore(tmp_path / "review.sqlite3")
    result = packet()
    store.create_run("RUN-001", result)
    with pytest.raises(ValidationError, match="TTL"):
        store.issue_challenge("RUN-001", result.decision_digest, ttl_seconds=ttl)


def test_symlink_database_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "target.sqlite3"
    target.touch()
    link = tmp_path / "link.sqlite3"
    link.symlink_to(target)
    with pytest.raises(SecurityBoundaryError, match="symlink"):
        ReviewStore(link)


def test_tampered_ledger_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "review.sqlite3"
    store = ReviewStore(path)
    result = packet()
    store.create_run("RUN-001", result)
    with closing(sqlite3.connect(path)) as connection:
        connection.execute(
            "UPDATE events SET payload_json = ? WHERE sequence = 1",
            (json.dumps({"tampered": True}),),
        )
        connection.commit()
    with pytest.raises(ValidationError, match="integrity"):
        store.verify_ledger()


def test_concurrent_review_allows_one_winner(tmp_path: Path) -> None:
    path = tmp_path / "review.sqlite3"
    store = ReviewStore(path)
    result = packet()
    store.create_run("RUN-001", result)
    challenge = store.issue_challenge(
        "RUN-001",
        result.decision_digest,
        nonce_factory=lambda: "c" * 32,
    )

    def attempt() -> str:
        try:
            ReviewStore(path).record_review(
                run_id="RUN-001",
                decision_digest=result.decision_digest,
                nonce=challenge.nonce,
                reviewer="Release Authority",
                action=ReviewAction.CONFIRM,
            )
            return "OK"
        except ReviewConflictError:
            return "CONFLICT"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = sorted(pool.map(lambda _: attempt(), range(2)))
    assert outcomes == ["CONFLICT", "OK"]


def test_generated_nonce_is_cli_safe_hex(tmp_path: Path) -> None:
    store = ReviewStore(tmp_path / "review.sqlite3")
    packet = GoLiveDecisionService(ROOT / "policy").decide(ROOT / "cases" / "pass")[0]
    store.create_run("RUN-NONCE", packet)
    challenge = store.issue_challenge("RUN-NONCE", packet.decision_digest)
    assert len(challenge.nonce) == 64
    assert all(character in "0123456789abcdef" for character in challenge.nonce)
