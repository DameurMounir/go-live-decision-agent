from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .domain import DecisionPacket, DecisionStatus
from .errors import ValidationError


@dataclass(frozen=True, slots=True)
class AdvisoryNote:
    adapter_id: str
    decision: DecisionStatus
    decision_digest: str
    summary: str
    authority: str = "ADVISORY_ONLY"


class DecisionAdvisor(Protocol):
    def advise(self, packet: DecisionPacket) -> AdvisoryNote: ...


class RuleAdvisor:
    adapter_id = "rule-advisor-v1"

    def advise(self, packet: DecisionPacket) -> AdvisoryNote:
        return AdvisoryNote(
            adapter_id=self.adapter_id,
            decision=packet.decision,
            decision_digest=packet.decision_digest,
            summary=(
                f"{packet.decision.value}: {len(packet.failed_gate_ids)} failed, "
                f"{len(packet.blocked_gate_ids)} blocked, and "
                f"{len(packet.passed_gate_ids)} satisfied mandatory gates."
            ),
        )


@dataclass(frozen=True, slots=True)
class FixtureAdvisor:
    response: AdvisoryNote

    def advise(self, packet: DecisionPacket) -> AdvisoryNote:
        del packet
        return self.response


def verify_advice(packet: DecisionPacket, note: AdvisoryNote) -> None:
    if note.authority != "ADVISORY_ONLY":
        raise ValidationError("advisor attempted to escalate authority")
    if note.decision != packet.decision:
        raise ValidationError("advisor attempted to change deterministic decision")
    if note.decision_digest != packet.decision_digest:
        raise ValidationError("advisor is bound to a stale or different decision packet")
    if not note.summary.strip():
        raise ValidationError("advisor summary is empty")
