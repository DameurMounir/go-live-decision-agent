#!/usr/bin/env python3
from __future__ import annotations

import sys
import tarfile
import zipfile
from pathlib import Path

FORBIDDEN_PARTS = {
    "artifacts",
    "build",
    "cases",
    "docs",
    "evaluation",
    "exports",
    "runs",
    "tests",
}
REQUIRED_PACKAGE_FILES = {
    "go_live_decision_agent/policy/gates.json",
    "go_live_decision_agent/sample_cases/pass/candidate.json",
    "go_live_decision_agent/sample_cases/blocked/candidate.json",
    "go_live_decision_agent/sample_cases/fail/candidate.json",
    "go_live_decision_agent/py.typed",
}


def names(path: Path) -> set[str]:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            return set(archive.namelist())
    with tarfile.open(path, "r:gz") as archive:
        raw = {member.name for member in archive.getmembers() if member.isfile()}
    prefixes = {name.split("/", 1)[0] for name in raw if "/" in name}
    if len(prefixes) != 1:
        raise SystemExit(f"sdist has unexpected roots: {sorted(prefixes)}")
    prefix = next(iter(prefixes))
    return {name[len(prefix) + 1 :] for name in raw if name.startswith(prefix + "/")}


def main() -> int:
    dist = Path(sys.argv[1] if len(sys.argv) > 1 else "dist")
    archives = sorted([*dist.glob("*.whl"), *dist.glob("*.tar.gz")])
    if len(archives) != 2:
        raise SystemExit(f"expected one wheel and one source distribution, found {len(archives)}")
    wheel = next(path for path in archives if path.suffix == ".whl")
    wheel_names = names(wheel)
    missing = REQUIRED_PACKAGE_FILES - wheel_names
    if missing:
        raise SystemExit(f"wheel missing required package files: {sorted(missing)}")
    for archive in archives:
        archive_names = names(archive)
        forbidden = {
            name
            for name in archive_names
            if any(part in FORBIDDEN_PARTS for part in Path(name).parts)
        }
        if forbidden:
            raise SystemExit(
                f"{archive.name} contains forbidden material: {sorted(forbidden)[:10]}"
            )
    print("PASS: wheel and source distribution contents verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
