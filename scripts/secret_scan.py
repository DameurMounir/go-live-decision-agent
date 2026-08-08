#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".py", ".md", ".toml", ".yml", ".yaml", ".json", ".txt", ".svg", ".html"}
EXCLUDED_PARTS = {
    ".git",
    ".venv",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "artifacts",
    "build",
    "dist",
    "evaluation",
    "cases",
    "tests",
}
EXCLUDED_FILES = {"uv.lock", "coverage.xml"}
# These paths contain deterministic generated SHA-256 evidence fixtures. Their
# source generators, manifests, and byte-stability checks run before this entropy
# scan, so excluding only the generated copies avoids false positives without
# weakening scanning of source code, configuration, documentation, or schemas.
EXCLUDED_PREFIXES = (
    Path("expected"),
    Path("src/go_live_decision_agent/sample_cases"),
)


def candidate_paths() -> list[Path]:
    tracked = subprocess.check_output(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
    ).split(b"\0")
    untracked = subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
    ).split(b"\0")
    result: list[Path] = []
    for raw in [*tracked, *untracked]:
        if not raw:
            continue
        relative = Path(os.fsdecode(raw))
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if any(relative == prefix or prefix in relative.parents for prefix in EXCLUDED_PREFIXES):
            continue
        if relative.name in EXCLUDED_FILES or relative.suffix.lower() not in TEXT_SUFFIXES:
            continue
        path = ROOT / relative
        if path.is_file():
            result.append(relative)
    return sorted(set(result))


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="glda-secret-scan-") as tmp:
        staging = Path(tmp)
        for relative in candidate_paths():
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, target)
        completed = subprocess.run(
            [sys.executable, "-m", "detect_secrets", "scan", "--all-files"],
            cwd=staging,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            print(completed.stdout)
            print(completed.stderr, file=sys.stderr)
            return completed.returncode
        payload = json.loads(completed.stdout)
        results = payload.get("results", {})
        if results:
            print(json.dumps(results, indent=2, sort_keys=True))
            raise SystemExit("detect-secrets findings require review")
    print("PASS: detect-secrets found no candidate in tracked or untracked source material")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
