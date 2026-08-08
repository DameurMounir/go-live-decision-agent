from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .domain import ReviewAction, ReviewState
from .errors import ValidationError


@dataclass(frozen=True, slots=True)
class ReviewChallenge:
    run_id: str
    decision_digest: str
    nonce: str
    issued_at: str
    expires_at: str

    def as_dict(self) -> dict[str, str]:
        return {
            "decision_digest": self.decision_digest,
            "expires_at": self.expires_at,
            "issued_at": self.issued_at,
            "nonce": self.nonce,
            "run_id": self.run_id,
        }


@dataclass(frozen=True, slots=True)
class ReviewRecord:
    run_id: str
    decision_digest: str
    reviewer: str
    action: ReviewAction
    comment: str
    reviewed_at: str
    state: ReviewState

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "comment": self.comment,
            "decision_digest": self.decision_digest,
            "reviewed_at": self.reviewed_at,
            "reviewer": self.reviewer,
            "run_id": self.run_id,
            "state": self.state.value,
        }


def state_for_action(action: ReviewAction) -> ReviewState:
    if action is ReviewAction.CONFIRM:
        return ReviewState.CONFIRMED
    if action is ReviewAction.REQUEST_REVISION:
        return ReviewState.REVISION_REQUESTED
    if action is ReviewAction.REJECT:
        return ReviewState.REJECTED
    raise ValidationError(f"unsupported review action: {action}")


def utc_now() -> datetime:
    return datetime.now(UTC)
