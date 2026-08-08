from pathlib import Path

from go_live_decision_agent.engine import verify_packet
from go_live_decision_agent.serialization import packet_from_dict
from go_live_decision_agent.service import GoLiveDecisionService

ROOT = Path(__file__).resolve().parents[1]


def test_packet_round_trip() -> None:
    packet, _ = GoLiveDecisionService(ROOT / "policy").decide(ROOT / "cases" / "blocked")
    restored = packet_from_dict(packet.as_dict())
    assert restored == packet
    verify_packet(restored)
