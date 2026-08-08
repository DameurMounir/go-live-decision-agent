from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any, cast

from .canonical import canonical_json_bytes, pretty_json, sha256_bytes
from .errors import ValidationError
from .paths import safe_child
from .store import ReviewStore

_MD_MARKER = re.compile(r"^<!-- decision-snapshot-sha256:([0-9a-f]{64}) -->$")
_HTML_MARKER = re.compile(r'<meta name="decision-snapshot-sha256" content="([0-9a-f]{64})">')


def _snapshot_digest(snapshot: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(snapshot))


def _markdown(snapshot: dict[str, Any], digest: str) -> str:
    packet = cast(dict[str, Any], snapshot["decision_packet"])
    lines = [
        f"<!-- decision-snapshot-sha256:{digest} -->",
        "# Go-Live Decision Packet",
        "",
        f"- Run: `{snapshot['run_id']}`",
        f"- Decision: **{packet['decision']}**",
        f"- Decision digest: `{packet['decision_digest']}`",
        f"- Human review state: `{snapshot['review_state']}`",
        "",
        "> " + str(snapshot["authority_boundary"]),
        "",
        "## Gate outcomes",
        "",
        "| Gate | Domain | Status | Reasons | Evidence |",
        "|---|---|---|---|---|",
    ]
    for gate in cast(list[dict[str, Any]], packet["gates"]):
        lines.append(
            "| {gate_id} | {domain} | {status} | {reasons} | {evidence} |".format(
                gate_id=gate["gate_id"],
                domain=gate["domain"],
                status=gate["status"],
                reasons=", ".join(cast(list[str], gate["reason_codes"])),
                evidence=", ".join(cast(list[str], gate["evidence_ids"])) or "—",
            )
        )
    lines.extend(["", "## Required actions", ""])
    lines.extend(f"- {item}" for item in cast(list[str], packet["required_actions"]))
    if not packet["required_actions"]:
        lines.append("- None.")
    lines.extend(["", "## Human review", ""])
    review = snapshot["review"]
    if review is None:
        lines.append("No human review has been recorded.")
    else:
        record = cast(dict[str, Any], review)
        lines.extend(
            [
                f"- Reviewer: `{record['reviewer']}`",
                f"- Action: `{record['action']}`",
                f"- Reviewed at: `{record['reviewed_at']}`",
                f"- Comment: {record['comment'] or '—'}",
            ]
        )
    return "\n".join(lines) + "\n"


def _html(snapshot: dict[str, Any], digest: str) -> str:
    packet = cast(dict[str, Any], snapshot["decision_packet"])
    rows: list[str] = []
    for gate in cast(list[dict[str, Any]], packet["gates"]):
        cells = [
            gate["gate_id"],
            gate["domain"],
            gate["status"],
            ", ".join(cast(list[str], gate["reason_codes"])),
            ", ".join(cast(list[str], gate["evidence_ids"])) or "—",
        ]
        rows.append(
            "<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in cells) + "</tr>"
        )
    review = snapshot["review"]
    if review is None:
        review_html = "<p>No human review has been recorded.</p>"
    else:
        record = cast(dict[str, Any], review)
        review_html = (
            "<ul>"
            f"<li>Reviewer: <code>{html.escape(str(record['reviewer']))}</code></li>"
            f"<li>Action: <code>{html.escape(str(record['action']))}</code></li>"
            f"<li>Reviewed at: <code>{html.escape(str(record['reviewed_at']))}</code></li>"
            f"<li>Comment: {html.escape(str(record['comment'] or '—'))}</li>"
            "</ul>"
        )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="decision-snapshot-sha256" content="{digest}">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Go-Live Decision Packet</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 1200px; margin: 2rem auto; padding: 0 1rem; }}
.banner {{ border: 1px solid #444; padding: 1rem; background: #f5f5f5; }}
.status {{ font-size: 2rem; font-weight: 700; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #aaa; padding: .5rem; text-align: left; vertical-align: top; }}
code {{ word-break: break-all; }}
</style>
</head>
<body>
<h1>Go-Live Decision Packet</h1>
<p class="status">{html.escape(str(packet["decision"]))}</p>
<p>Run: <code>{html.escape(str(snapshot["run_id"]))}</code><br>
Decision digest: <code>{html.escape(str(packet["decision_digest"]))}</code><br>
Review state: <code>{html.escape(str(snapshot["review_state"]))}</code></p>
<div class="banner">{html.escape(str(snapshot["authority_boundary"]))}</div>
<h2>Gate outcomes</h2>
<table><thead><tr><th>Gate</th><th>Domain</th><th>Status</th><th>Reasons</th><th>Evidence</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table>
<h2>Human review</h2>
{review_html}
</body>
</html>
"""


def write_exports(store: ReviewStore, run_id: str, output_dir: Path) -> dict[str, Path]:
    snapshot = store.snapshot(run_id)
    digest = _snapshot_digest(snapshot)
    payload = {"snapshot": snapshot, "snapshot_sha256": digest}
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = safe_child(output_dir, f"{run_id}.json")
    markdown_path = safe_child(output_dir, f"{run_id}.md")
    html_path = safe_child(output_dir, f"{run_id}.html")
    json_path.write_text(pretty_json(payload), encoding="utf-8")
    markdown_path.write_text(_markdown(snapshot, digest), encoding="utf-8")
    html_path.write_text(_html(snapshot, digest), encoding="utf-8")
    return {"html": html_path, "json": json_path, "markdown": markdown_path}


def verify_export_equivalence(
    json_path: Path,
    markdown_path: Path,
    html_path: Path,
) -> str:
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("snapshot"), dict):
        raise ValidationError("JSON export is invalid")
    expected = str(payload.get("snapshot_sha256"))
    actual = _snapshot_digest(cast(dict[str, Any], payload["snapshot"]))
    if expected != actual:
        raise ValidationError("JSON export digest mismatch")
    first_line = markdown_path.read_text(encoding="utf-8").splitlines()[0]
    md_match = _MD_MARKER.fullmatch(first_line)
    html_match = _HTML_MARKER.search(html_path.read_text(encoding="utf-8"))
    if md_match is None or html_match is None:
        raise ValidationError("export digest marker missing")
    if {expected, md_match.group(1), html_match.group(1)} != {expected}:
        raise ValidationError("JSON, Markdown, and HTML exports are not equivalent")
    html_text = html_path.read_text(encoding="utf-8").lower()
    if "<script" in html_text or "http://" in html_text or "https://" in html_text:
        raise ValidationError("HTML export contains an external or active dependency")
    return expected
