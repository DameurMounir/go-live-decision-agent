from __future__ import annotations

from .paths import packaged_cases_dir, packaged_policy_dir
from .service import GoLiveDecisionService


def render() -> None:
    import streamlit as st

    st.set_page_config(page_title="Go-Live Decision Room", layout="wide")
    st.title("Go-Live Decision Room")
    st.caption("Evidence-bound decision support. Human release authority remains accountable.")

    scenario = st.selectbox("Frozen scenario", ["blocked", "pass", "fail"])
    packet, note = GoLiveDecisionService(packaged_policy_dir()).decide(
        packaged_cases_dir() / scenario
    )

    a, b, c, d = st.columns(4)
    a.metric("Decision", packet.decision.value)
    b.metric("Failed gates", len(packet.failed_gate_ids))
    c.metric("Blocked gates", len(packet.blocked_gate_ids))
    d.metric("Satisfied gates", len(packet.passed_gate_ids))

    st.warning(packet.authority_boundary)
    st.info(note.summary)

    tabs = st.tabs(["Gate register", "Evidence reasons", "Actions", "Digest"])
    with tabs[0]:
        st.dataframe(
            [gate.as_dict() for gate in packet.gates],
            use_container_width=True,
            hide_index=True,
        )
    with tabs[1]:
        selected = st.selectbox("Gate", [gate.gate_id for gate in packet.gates])
        gate = next(item for item in packet.gates if item.gate_id == selected)
        st.json(gate.as_dict())
    with tabs[2]:
        st.write(list(packet.required_actions) or ["No mandatory remediation action."])
        st.write(list(packet.residual_risks) or ["No waived residual risk."])
    with tabs[3]:
        st.code(packet.decision_digest)
        st.caption(
            "Any evidence, policy, gate outcome, or candidate change produces another digest."
        )


def main() -> None:
    render()
