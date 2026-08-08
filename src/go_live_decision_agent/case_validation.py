from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, cast

from .canonical import canonical_json_bytes, sha256_bytes, sha256_file
from .errors import ValidationError

_ALLOWED_SCENARIOS = {"pass", "blocked", "fail"}
_ALLOWED_EVIDENCE_STATUS = {"PASS", "FAIL"}
_ALLOWED_APPROVAL_STATE = {"APPROVED", "PENDING", "REJECTED"}


@dataclass(frozen=True, slots=True)
class ValidatedCase:
    case_dir: Path
    candidate: Mapping[str, Any]
    evidence: tuple[Mapping[str, Any], ...]
    waivers: tuple[Mapping[str, Any], ...]


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"invalid JSON file: {path}") from exc


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValidationError(f"{field} must be a non-empty string")
    return value


def _validate_manifest(case_dir: Path, manifest: Mapping[str, Any]) -> None:
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise ValidationError("manifest files must be a non-empty list")
    expected = {"candidate.json", "evidence.json", "waivers.json"}
    seen: set[str] = set()
    for record in files:
        if not isinstance(record, dict):
            raise ValidationError("manifest record must be an object")
        relative = _require_text(record.get("path"), "manifest path")
        if relative in seen:
            raise ValidationError(f"duplicate manifest path: {relative}")
        if "/" in relative or "\\" in relative or relative.startswith("."):
            raise ValidationError(f"unsafe manifest path: {relative}")
        path = case_dir / relative
        if not path.is_file() or path.is_symlink():
            raise ValidationError(f"manifest file missing or unsafe: {relative}")
        if int(record.get("bytes", -1)) != path.stat().st_size:
            raise ValidationError(f"manifest byte count mismatch: {relative}")
        if _require_text(record.get("sha256"), "manifest sha256") != sha256_file(path):
            raise ValidationError(f"manifest digest mismatch: {relative}")
        seen.add(relative)
    if seen != expected:
        raise ValidationError(f"manifest coverage mismatch: {sorted(seen)}")


def _validate_evidence_item(
    item: Mapping[str, Any],
    *,
    candidate_id: str,
    candidate_version: str,
) -> None:
    evidence_id = _require_text(item.get("evidence_id"), "evidence_id")
    gate_id = _require_text(item.get("gate_id"), f"{evidence_id}.gate_id")
    if not gate_id.startswith("G-"):
        raise ValidationError(f"invalid gate identifier: {gate_id}")
    if item.get("status") not in _ALLOWED_EVIDENCE_STATUS:
        raise ValidationError(f"invalid evidence status: {evidence_id}")
    if item.get("approval_state") not in _ALLOWED_APPROVAL_STATE:
        raise ValidationError(f"invalid approval state: {evidence_id}")
    if item.get("candidate_id") != candidate_id:
        raise ValidationError(f"evidence candidate mismatch: {evidence_id}")
    if item.get("candidate_version") != candidate_version:
        raise ValidationError(f"evidence version mismatch: {evidence_id}")
    for field in ("title", "owner", "issuer", "assertion", "source_type"):
        _require_text(item.get(field), f"{evidence_id}.{field}")
    try:
        observed_at = date.fromisoformat(
            _require_text(item.get("observed_at"), f"{evidence_id}.observed_at")
        )
        expires_at = date.fromisoformat(
            _require_text(item.get("expires_at"), f"{evidence_id}.expires_at")
        )
    except ValueError as exc:
        raise ValidationError(f"invalid evidence date: {evidence_id}") from exc
    if expires_at < observed_at:
        raise ValidationError(f"evidence expires before observation: {evidence_id}")
    payload_digest = _require_text(item.get("payload_sha256"), f"{evidence_id}.payload_sha256")
    unsigned = dict(item)
    unsigned.pop("payload_sha256", None)
    if payload_digest != sha256_bytes(canonical_json_bytes(unsigned)):
        raise ValidationError(f"evidence payload digest mismatch: {evidence_id}")


def validate_case(case_dir: Path) -> ValidatedCase:
    if case_dir.is_symlink():
        raise ValidationError(f"case directory missing or unsafe: {case_dir}")
    case_dir = case_dir.resolve()
    if not case_dir.is_dir():
        raise ValidationError(f"case directory missing or unsafe: {case_dir}")
    manifest_raw = _load_json(case_dir / "manifest.json")
    if not isinstance(manifest_raw, dict):
        raise ValidationError("manifest must be an object")
    manifest = cast(Mapping[str, Any], manifest_raw)
    _validate_manifest(case_dir, manifest)

    candidate_raw = _load_json(case_dir / "candidate.json")
    evidence_raw = _load_json(case_dir / "evidence.json")
    waivers_raw = _load_json(case_dir / "waivers.json")
    if not isinstance(candidate_raw, dict):
        raise ValidationError("candidate must be an object")
    if not isinstance(evidence_raw, dict) or not isinstance(evidence_raw.get("evidence"), list):
        raise ValidationError("evidence file must contain an evidence list")
    if not isinstance(waivers_raw, dict) or not isinstance(waivers_raw.get("waivers"), list):
        raise ValidationError("waivers file must contain a waivers list")

    candidate = cast(Mapping[str, Any], candidate_raw)
    scenario = _require_text(candidate.get("scenario"), "scenario")
    if scenario not in _ALLOWED_SCENARIOS or manifest.get("scenario") != scenario:
        raise ValidationError(f"invalid or inconsistent scenario: {scenario}")
    candidate_id = _require_text(candidate.get("candidate_id"), "candidate_id")
    candidate_version = _require_text(candidate.get("candidate_version"), "candidate_version")
    try:
        date.fromisoformat(_require_text(candidate.get("assessment_date"), "assessment_date"))
    except ValueError as exc:
        raise ValidationError("invalid assessment_date") from exc

    evidence_items: list[Mapping[str, Any]] = []
    seen_evidence: set[str] = set()
    for raw in cast(list[object], evidence_raw["evidence"]):
        if not isinstance(raw, dict):
            raise ValidationError("evidence item must be an object")
        item = cast(Mapping[str, Any], raw)
        _validate_evidence_item(
            item,
            candidate_id=candidate_id,
            candidate_version=candidate_version,
        )
        evidence_id = cast(str, item["evidence_id"])
        if evidence_id in seen_evidence:
            raise ValidationError(f"duplicate evidence identifier: {evidence_id}")
        seen_evidence.add(evidence_id)
        evidence_items.append(item)

    waivers: list[Mapping[str, Any]] = []
    for raw in cast(list[object], waivers_raw["waivers"]):
        if not isinstance(raw, dict):
            raise ValidationError("waiver must be an object")
        waivers.append(cast(Mapping[str, Any], raw))

    return ValidatedCase(
        case_dir=case_dir,
        candidate=candidate,
        evidence=tuple(evidence_items),
        waivers=tuple(waivers),
    )
