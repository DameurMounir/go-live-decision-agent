#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def run(command: Sequence[str], *, env: dict[str, str] | None = None) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True, env=env)


def clean_generated() -> None:
    for path in (
        ROOT / ".mypy_cache",
        ROOT / ".pytest_cache",
        ROOT / ".ruff_cache",
        ROOT / "build",
        ROOT / "dist",
        ROOT / "artifacts" / "release-evidence",
    ):
        shutil.rmtree(path, ignore_errors=True)
    for path in ROOT.glob(".coverage*"):
        path.unlink(missing_ok=True)


def smoke_wheel() -> None:
    wheels = sorted((ROOT / "dist").glob("*.whl"))
    if len(wheels) != 1:
        raise SystemExit("expected exactly one wheel for smoke test")
    uv = shutil.which("uv")
    if uv is None:
        raise SystemExit("uv is required for isolated wheel smoke testing")
    with tempfile.TemporaryDirectory(prefix="glda-wheel-smoke-") as tmp:
        venv = Path(tmp) / "venv"
        run([uv, "venv", "--python", PYTHON, str(venv)])
        executable = venv / "bin" / "python"
        run([uv, "pip", "install", "--python", str(executable), "--no-deps", str(wheels[0])])
        code = (
            "from go_live_decision_agent.paths import packaged_cases_dir, packaged_policy_dir;"
            "from go_live_decision_agent.service import GoLiveDecisionService;"
            "s=GoLiveDecisionService(packaged_policy_dir());"
            "assert s.decide(packaged_cases_dir()/'pass')[0].decision.value=='PASS';"
            "assert s.decide(packaged_cases_dir()/'blocked')[0].decision.value=='BLOCKED';"
            "assert s.decide(packaged_cases_dir()/'fail')[0].decision.value=='FAIL';"
            "print('PASS: wheel decisions verified')"
        )
        run([str(executable), "-c", code])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ci", action="store_true")
    args = parser.parse_args()
    del args

    clean_generated()
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["MYPY_CACHE_DIR"] = "/tmp/glda-mypy-cache"
    env["RUFF_CACHE_DIR"] = "/tmp/glda-ruff-cache"
    env["COVERAGE_FILE"] = "/tmp/glda-coverage"
    env["PYTEST_ADDOPTS"] = "-p no:cacheprovider"

    checks = [
        [PYTHON, "scripts/build_cases.py", "--check"],
        [PYTHON, "scripts/verify_cases.py"],
        [PYTHON, "scripts/generate_contracts.py", "--check"],
        [PYTHON, "scripts/generate_decisions.py", "--check"],
        [PYTHON, "scripts/sync_package_assets.py", "--check"],
        [PYTHON, "scripts/evaluate.py", "--check"],
    ]
    if (ROOT / "scripts" / "generate_public_artifacts.py").is_file():
        checks.extend(
            [
                [PYTHON, "scripts/generate_public_artifacts.py", "--check"],
                [PYTHON, "scripts/verify_public_claims.py"],
            ]
        )
    checks.extend(
        [
            [PYTHON, "scripts/scan_public_boundary.py"],
            [PYTHON, "scripts/check_links.py"],
            [PYTHON, "-m", "ruff", "format", "--check", "."],
            [PYTHON, "-m", "ruff", "check", "."],
            [PYTHON, "-m", "mypy", "src", "scripts"],
            [
                PYTHON,
                "-m",
                "pytest",
                "--cov=go_live_decision_agent",
                "--cov-branch",
                "--cov-report=term-missing",
                "--cov-report=xml:artifacts/release-evidence/coverage.xml",
                "--cov-fail-under=90",
            ],
            [PYTHON, "-m", "bandit", "-q", "-r", "src", "-lll"],
            [PYTHON, "scripts/secret_scan.py"],
            [
                PYTHON,
                "-m",
                "pip_audit",
                "--local",
                "--skip-editable",
                "--format",
                "json",
            ],
        ]
    )
    for command in checks:
        run(command, env=env)

    run([PYTHON, "-m", "build"], env=env)
    archives = [str(path) for path in sorted((ROOT / "dist").glob("*")) if path.is_file()]
    run([PYTHON, "-m", "twine", "check", *archives], env=env)
    run([PYTHON, "scripts/check_dist.py", "dist"], env=env)
    smoke_wheel()
    run(["git", "diff", "--exit-code"], env=env)
    print("PASS: complete deterministic release gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
