from __future__ import annotations

import json
import secrets
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from .canonical import canonical_json_bytes, pretty_json, sha256_bytes
from .domain import DecisionPacket, ReviewAction, ReviewState
from .errors import ReviewConflictError, SecurityBoundaryError, ValidationError
from .review import ReviewChallenge, ReviewRecord, state_for_action, utc_now
from .serialization import packet_from_dict


class ReviewStore:
    def __init__(self, path: Path, *, clock: Callable[[], datetime] = utc_now) -> None:
        self.path = path.resolve()
        self._clock = clock
        if path.exists() and path.is_symlink():
            raise SecurityBoundaryError(f"review database may not be a symlink: {path}")
        if path.parent.exists() and path.parent.is_symlink():
            raise SecurityBoundaryError(
                f"review database parent may not be a symlink: {path.parent}"
            )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    decision_digest TEXT NOT NULL,
                    packet_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS challenges (
                    nonce TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    decision_digest TEXT NOT NULL,
                    issued_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    consumed_at TEXT,
                    superseded INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS reviews (
                    run_id TEXT PRIMARY KEY REFERENCES runs(run_id),
                    decision_digest TEXT NOT NULL,
                    nonce TEXT NOT NULL UNIQUE REFERENCES challenges(nonce),
                    reviewer TEXT NOT NULL,
                    action TEXT NOT NULL,
                    comment TEXT NOT NULL,
                    reviewed_at TEXT NOT NULL,
                    state TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL UNIQUE
                );
                """
            )

    def _append_event(
        self,
        connection: sqlite3.Connection,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        previous_row = connection.execute(
            "SELECT event_hash FROM events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        previous_hash = "" if previous_row is None else str(previous_row["event_hash"])
        payload_json = pretty_json(payload)
        event_hash = sha256_bytes(
            canonical_json_bytes(
                {
                    "event_type": event_type,
                    "payload": payload,
                    "previous_hash": previous_hash,
                }
            )
        )
        connection.execute(
            """
            INSERT INTO events(event_type, payload_json, previous_hash, event_hash)
            VALUES (?, ?, ?, ?)
            """,
            (event_type, payload_json, previous_hash, event_hash),
        )

    def create_run(self, run_id: str, packet: DecisionPacket) -> None:
        created_at = self._clock().astimezone(UTC).isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT decision_digest FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row is not None:
                if str(row["decision_digest"]) != packet.decision_digest:
                    raise ReviewConflictError(
                        f"run identifier already binds another packet: {run_id}"
                    )
                connection.execute("COMMIT")
                return
            connection.execute(
                """
                INSERT INTO runs(run_id, decision_digest, packet_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (run_id, packet.decision_digest, pretty_json(packet.as_dict()), created_at),
            )
            self._append_event(
                connection,
                "RUN_CREATED",
                {
                    "decision": packet.decision.value,
                    "decision_digest": packet.decision_digest,
                    "run_id": run_id,
                },
            )
            connection.execute("COMMIT")

    def issue_challenge(
        self,
        run_id: str,
        decision_digest: str,
        *,
        ttl_seconds: int = 600,
        nonce_factory: Callable[[], str] | None = None,
    ) -> ReviewChallenge:
        if ttl_seconds < 60 or ttl_seconds > 3600:
            raise ValidationError("challenge TTL must be between 60 and 3600 seconds")
        now = self._clock().astimezone(UTC)
        nonce = (nonce_factory or (lambda: secrets.token_hex(32)))()
        if len(nonce) < 32:
            raise ValidationError("review nonce must be at least 32 characters")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            run = connection.execute(
                "SELECT decision_digest FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if run is None:
                raise ReviewConflictError(f"unknown run: {run_id}")
            if str(run["decision_digest"]) != decision_digest:
                raise ReviewConflictError("challenge digest does not match the stored packet")
            if connection.execute("SELECT 1 FROM reviews WHERE run_id = ?", (run_id,)).fetchone():
                raise ReviewConflictError("run already has a final human review")
            connection.execute(
                "UPDATE challenges SET superseded = 1 WHERE run_id = ? AND consumed_at IS NULL",
                (run_id,),
            )
            issued_at = now.isoformat()
            expires_at = (now + timedelta(seconds=ttl_seconds)).isoformat()
            connection.execute(
                """
                INSERT INTO challenges(
                    nonce, run_id, decision_digest, issued_at, expires_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (nonce, run_id, decision_digest, issued_at, expires_at),
            )
            challenge = ReviewChallenge(
                run_id=run_id,
                decision_digest=decision_digest,
                nonce=nonce,
                issued_at=issued_at,
                expires_at=expires_at,
            )
            self._append_event(connection, "CHALLENGE_ISSUED", challenge.as_dict())
            connection.execute("COMMIT")
            return challenge

    def record_review(
        self,
        *,
        run_id: str,
        decision_digest: str,
        nonce: str,
        reviewer: str,
        action: ReviewAction,
        comment: str = "",
    ) -> ReviewRecord:
        if not reviewer.strip():
            raise ValidationError("reviewer is required")
        if len(comment) > 2000:
            raise ValidationError("review comment exceeds 2000 characters")
        now = self._clock().astimezone(UTC)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            run = connection.execute(
                "SELECT decision_digest FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if run is None:
                raise ReviewConflictError(f"unknown run: {run_id}")
            if str(run["decision_digest"]) != decision_digest:
                raise ReviewConflictError("review digest is stale or belongs to another packet")
            if connection.execute("SELECT 1 FROM reviews WHERE run_id = ?", (run_id,)).fetchone():
                raise ReviewConflictError("run already has a final human review")
            challenge = connection.execute(
                "SELECT * FROM challenges WHERE nonce = ?", (nonce,)
            ).fetchone()
            if challenge is None or str(challenge["run_id"]) != run_id:
                raise ReviewConflictError("review challenge is unknown")
            if int(challenge["superseded"]) == 1:
                raise ReviewConflictError("review challenge was superseded")
            if challenge["consumed_at"] is not None:
                raise ReviewConflictError("review challenge was already consumed")
            if str(challenge["decision_digest"]) != decision_digest:
                raise ReviewConflictError("review challenge digest mismatch")
            expires_at = datetime.fromisoformat(str(challenge["expires_at"]))
            if now > expires_at:
                raise ReviewConflictError("review challenge expired")

            reviewed_at = now.isoformat()
            state = state_for_action(action)
            connection.execute(
                """
                INSERT INTO reviews(
                    run_id, decision_digest, nonce, reviewer, action, comment,
                    reviewed_at, state
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    decision_digest,
                    nonce,
                    reviewer.strip(),
                    action.value,
                    comment,
                    reviewed_at,
                    state.value,
                ),
            )
            connection.execute(
                "UPDATE challenges SET consumed_at = ? WHERE nonce = ?",
                (reviewed_at, nonce),
            )
            record = ReviewRecord(
                run_id=run_id,
                decision_digest=decision_digest,
                reviewer=reviewer.strip(),
                action=action,
                comment=comment,
                reviewed_at=reviewed_at,
                state=state,
            )
            self._append_event(connection, "REVIEW_RECORDED", record.as_dict())
            connection.execute("COMMIT")
            return record

    def load_packet(self, run_id: str) -> DecisionPacket:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT packet_json FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise ReviewConflictError(f"unknown run: {run_id}")
        payload = json.loads(str(row["packet_json"]))
        if not isinstance(payload, dict):
            raise ValidationError("stored packet is invalid")
        return packet_from_dict(cast(dict[str, Any], payload))

    def review_for_run(self, run_id: str) -> ReviewRecord | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM reviews WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        return ReviewRecord(
            run_id=str(row["run_id"]),
            decision_digest=str(row["decision_digest"]),
            reviewer=str(row["reviewer"]),
            action=ReviewAction(str(row["action"])),
            comment=str(row["comment"]),
            reviewed_at=str(row["reviewed_at"]),
            state=ReviewState(str(row["state"])),
        )

    def snapshot(self, run_id: str) -> dict[str, Any]:
        packet = self.load_packet(run_id)
        review = self.review_for_run(run_id)
        state = ReviewState.UNREVIEWED if review is None else review.state
        return {
            "authority_boundary": packet.authority_boundary,
            "decision_packet": packet.as_dict(),
            "export_status": "DRAFT" if review is None else "HUMAN_REVIEWED",
            "review": None if review is None else review.as_dict(),
            "review_state": state.value,
            "run_id": run_id,
        }

    def verify_ledger(self) -> None:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM events ORDER BY sequence").fetchall()
        previous_hash = ""
        for row in rows:
            payload = json.loads(str(row["payload_json"]))
            expected = sha256_bytes(
                canonical_json_bytes(
                    {
                        "event_type": str(row["event_type"]),
                        "payload": payload,
                        "previous_hash": previous_hash,
                    }
                )
            )
            if str(row["previous_hash"]) != previous_hash or str(row["event_hash"]) != expected:
                raise ValidationError(f"review ledger integrity failure at event {row['sequence']}")
            previous_hash = expected
