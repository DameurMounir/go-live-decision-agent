#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*command: str) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    for cache in (".mypy_cache", ".pytest_cache", ".ruff_cache"):
        shutil.rmtree(ROOT / cache, ignore_errors=True)
    if (ROOT / "scripts" / "release_gate.py").is_file():
        run(sys.executable, "scripts/release_gate.py", "--ci")
        return 0
    run(sys.executable, "-m", "compileall", "-q", "src", "scripts", "tests")
    run(sys.executable, "-m", "ruff", "format", "--check", ".")
    run(sys.executable, "-m", "ruff", "check", ".")
    run(sys.executable, "-m", "mypy", "src", "scripts")
    run(sys.executable, "-m", "pytest", "-q")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
