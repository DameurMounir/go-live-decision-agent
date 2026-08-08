from __future__ import annotations

from pathlib import Path

from .adapters import AdvisoryNote, DecisionAdvisor, RuleAdvisor, verify_advice
from .case_validation import validate_case
from .domain import DecisionPacket
from .engine import evaluate_case, verify_packet
from .policy import load_policy


class GoLiveDecisionService:
    def __init__(self, policy_dir: Path, advisor: DecisionAdvisor | None = None) -> None:
        self._policy_dir = policy_dir
        self._advisor = advisor or RuleAdvisor()

    def decide(self, case_dir: Path) -> tuple[DecisionPacket, AdvisoryNote]:
        case = validate_case(case_dir)
        policy = load_policy(self._policy_dir)
        packet = evaluate_case(case, policy)
        verify_packet(packet)
        note = self._advisor.advise(packet)
        verify_advice(packet, note)
        return packet, note
