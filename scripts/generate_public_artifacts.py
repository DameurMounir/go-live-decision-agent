#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"


def svg(width: int, height: int, body: str, title: str) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
<title id="title">{escape(title)}</title>
<desc id="desc">Deterministically generated synthetic portfolio diagram.</desc>
<rect width="100%" height="100%" fill="#f8fafc"/>
{body}
</svg>
"""


def text(
    x: int, y: int, value: str, *, size: int = 18, weight: int = 400, anchor: str = "start"
) -> str:
    return (
        f'<text x="{x}" y="{y}" font-family="system-ui, sans-serif" '
        f'font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" '
        f'fill="#0f172a">{escape(value)}</text>'
    )


def box(x: int, y: int, width: int, height: int, label: str, subtitle: str = "") -> str:
    parts = [
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="12" fill="#ffffff" stroke="#334155" stroke-width="2"/>',
        text(x + width // 2, y + 34, label, size=20, weight=700, anchor="middle"),
    ]
    if subtitle:
        parts.append(text(x + width // 2, y + 61, subtitle, size=14, anchor="middle"))
    return "\n".join(parts)


def arrow(x1: int, y1: int, x2: int, y2: int) -> str:
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#475569" stroke-width="3"/>'
        f'<polygon points="{x2},{y2} {x2 - 10},{y2 - 6} {x2 - 10},{y2 + 6}" fill="#475569"/>'
    )


def artifacts() -> dict[str, str]:
    precedence = svg(
        1000,
        300,
        "\n".join(
            [
                box(50, 90, 250, 100, "FAIL", "valid explicit failure"),
                arrow(310, 140, 390, 140),
                box(400, 90, 250, 100, "BLOCKED", "evidence or authority gap"),
                arrow(660, 140, 740, 140),
                box(750, 90, 200, 100, "PASS", "all mandatory gates satisfied"),
                text(500, 45, "Decision precedence", size=28, weight=700, anchor="middle"),
            ]
        ),
        "FAIL, BLOCKED, PASS decision precedence",
    )

    gate_labels = [
        "Identity",
        "Business",
        "Functional",
        "Security",
        "Privacy",
        "Migration",
        "Performance",
        "Reliability",
        "Observability",
        "Support",
        "Change",
        "Rollback",
        "Supplier",
        "Authority",
    ]
    gate_body = [
        text(700, 45, "Fourteen mandatory readiness gates", size=28, weight=700, anchor="middle")
    ]
    for index, label in enumerate(gate_labels):
        row, col = divmod(index, 7)
        gate_body.append(box(30 + col * 195, 80 + row * 120, 170, 80, f"G-{index + 1:02d}", label))
    gate_map = svg(1400, 350, "\n".join(gate_body), "Fourteen readiness gates")

    workflow_labels = [
        ("Candidate + evidence", "frozen and hashed"),
        ("Validate", "identity, dates, approval"),
        ("Evaluate gates", "reason + evidence trace"),
        ("Precedence", "FAIL > BLOCKED > PASS"),
        ("Human review", "digest + one-use nonce"),
        ("Exports", "JSON · Markdown · HTML"),
    ]
    workflow_body = [
        text(700, 42, "Evidence-bound go-live workflow", size=28, weight=700, anchor="middle")
    ]
    for index, (label, subtitle) in enumerate(workflow_labels):
        x = 30 + index * 225
        workflow_body.append(box(x, 95, 180, 100, label, subtitle))
        if index < len(workflow_labels) - 1:
            workflow_body.append(arrow(x + 185, 145, x + 215, 145))
    workflow = svg(1400, 260, "\n".join(workflow_body), "Go-live decision workflow")

    interface = svg(
        1400,
        760,
        "\n".join(
            [
                text(50, 55, "Go-Live Decision Room", size=30, weight=700),
                text(50, 88, "Synthetic blocked scenario · advisory only", size=17),
                box(50, 120, 250, 110, "BLOCKED", "overall decision"),
                box(330, 120, 250, 110, "0", "failed gates"),
                box(610, 120, 250, 110, "3", "blocked gates"),
                box(890, 120, 250, 110, "11", "satisfied gates"),
                '<rect x="50" y="270" width="1290" height="70" rx="10" fill="#fff7ed" stroke="#c2410c" stroke-width="2"/>',
                text(
                    75,
                    312,
                    "ADVISORY ONLY — human release authority remains accountable.",
                    size=18,
                    weight=700,
                ),
                text(50, 390, "Gate register", size=24, weight=700),
                '<rect x="50" y="420" width="1290" height="260" rx="10" fill="#ffffff" stroke="#64748b"/>',
                text(80, 458, "Gate", size=16, weight=700),
                text(250, 458, "Domain", size=16, weight=700),
                text(520, 458, "Status", size=16, weight=700),
                text(720, 458, "Reason", size=16, weight=700),
                text(80, 505, "G-11", size=16),
                text(250, 505, "CHANGE_READINESS", size=16),
                text(520, 505, "BLOCKED", size=16, weight=700),
                text(720, 505, "EVIDENCE_STALE", size=16),
                text(80, 555, "G-13", size=16),
                text(250, 555, "SUPPLY_CHAIN", size=16),
                text(520, 555, "BLOCKED", size=16, weight=700),
                text(720, 555, "MISSING_REQUIRED_EVIDENCE", size=16),
                text(80, 605, "G-14", size=16),
                text(250, 605, "RELEASE_GOVERNANCE", size=16),
                text(520, 605, "BLOCKED", size=16, weight=700),
                text(720, 605, "APPROVAL_PENDING", size=16),
                text(50, 720, "Decision digest: 64-character canonical SHA-256", size=16),
            ]
        ),
        "Go-Live Decision Room preview",
    )

    social = svg(
        1280,
        640,
        "\n".join(
            [
                text(70, 100, "Go-Live Decision Agent", size=48, weight=800),
                text(70, 155, "Is there enough evidence to proceed?", size=28),
                box(70, 230, 300, 150, "PASS", "all mandatory evidence satisfied"),
                box(490, 230, 300, 150, "BLOCKED", "decision evidence incomplete"),
                box(910, 230, 300, 150, "FAIL", "mandatory evidence failed"),
                text(
                    640,
                    470,
                    "Deterministic gates · evidence digests · human authority",
                    size=24,
                    weight=700,
                    anchor="middle",
                ),
                text(
                    640,
                    525,
                    "Synthetic public BSA and agentic-engineering case study",
                    size=20,
                    anchor="middle",
                ),
            ]
        ),
        "Go-Live Decision Agent social preview",
    )

    return {
        "decision-precedence.svg": precedence,
        "gate-map.svg": gate_map,
        "interface-preview.svg": interface,
        "social-preview.svg": social,
        "workflow.svg": workflow,
    }


def write_into(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for name, content in artifacts().items():
        (root / name).write_text(content, encoding="utf-8")


def tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes() for path in sorted(root.rglob("*.svg"))
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        with tempfile.TemporaryDirectory() as tmp:
            generated = Path(tmp)
            write_into(generated)
            if tree(generated) != tree(ASSETS):
                raise SystemExit("public SVG artifacts differ from committed artifacts")
        print("PASS: public SVG artifacts are byte-stable")
        return 0
    shutil.rmtree(ASSETS, ignore_errors=True)
    write_into(ASSETS)
    print("PASS: generated deterministic public SVG artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
