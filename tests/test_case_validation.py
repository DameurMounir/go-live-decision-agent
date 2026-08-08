from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from go_live_decision_agent.case_validation import validate_case
from go_live_decision_agent.errors import ValidationError

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(("scenario", "count"), [("pass", 14), ("blocked", 13), ("fail", 14)])
def test_frozen_case_validates(scenario: str, count: int) -> None:
    case = validate_case(ROOT / "cases" / scenario)
    assert len(case.evidence) == count
    assert case.candidate["scenario"] == scenario


@pytest.mark.parametrize("scenario", ["pass", "blocked", "fail"])
def test_manifest_covers_exact_source_files(scenario: str) -> None:
    payload = json.loads((ROOT / "cases" / scenario / "manifest.json").read_text())
    assert {item["path"] for item in payload["files"]} == {
        "candidate.json",
        "evidence.json",
        "waivers.json",
    }


def _copy_case(tmp_path: Path, scenario: str = "pass") -> Path:
    target = tmp_path / scenario
    shutil.copytree(ROOT / "cases" / scenario, target)
    return target


def test_tampered_evidence_file_is_rejected(tmp_path: Path) -> None:
    target = _copy_case(tmp_path)
    path = target / "evidence.json"
    path.write_text(path.read_text().replace("APPROVED", "PENDING", 1))
    with pytest.raises(ValidationError, match="manifest"):
        validate_case(target)


def test_tampered_payload_digest_is_rejected(tmp_path: Path) -> None:
    target = _copy_case(tmp_path)
    path = target / "evidence.json"
    payload = json.loads(path.read_text())
    payload["evidence"][0]["payload_sha256"] = "0" * 64
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    import hashlib

    for record in manifest["files"]:
        if record["path"] == "evidence.json":
            record["bytes"] = path.stat().st_size
            record["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    with pytest.raises(ValidationError, match="payload digest"):
        validate_case(target)


@pytest.mark.parametrize("unsafe", ["../candidate.json", "/tmp/x", ".hidden"])
def test_unsafe_manifest_path_is_rejected(tmp_path: Path, unsafe: str) -> None:
    target = _copy_case(tmp_path)
    manifest_path = target / "manifest.json"
    payload = json.loads(manifest_path.read_text())
    payload["files"][0]["path"] = unsafe
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    with pytest.raises(ValidationError, match="unsafe manifest path"):
        validate_case(target)


def test_candidate_version_mismatch_is_rejected(tmp_path: Path) -> None:
    target = _copy_case(tmp_path)
    evidence_path = target / "evidence.json"
    evidence = json.loads(evidence_path.read_text())
    evidence["evidence"][0]["candidate_version"] = "other"
    unsigned = dict(evidence["evidence"][0])
    unsigned.pop("payload_sha256")
    import hashlib

    canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    evidence["evidence"][0]["payload_sha256"] = hashlib.sha256(canonical).hexdigest()
    evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for record in manifest["files"]:
        if record["path"] == "evidence.json":
            record["bytes"] = evidence_path.stat().st_size
            record["sha256"] = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    with pytest.raises(ValidationError, match="version mismatch"):
        validate_case(target)
