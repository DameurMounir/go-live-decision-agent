#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "go_live_decision_agent"


def copy_into(package: Path) -> None:
    shutil.copytree(ROOT / "cases", package / "sample_cases", dirs_exist_ok=True)
    shutil.copytree(ROOT / "policy", package / "policy", dirs_exist_ok=True)


def tree(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        with tempfile.TemporaryDirectory() as tmp:
            generated = Path(tmp)
            copy_into(generated)
            expected = {
                **{f"sample_cases/{k}": v for k, v in tree(generated / "sample_cases").items()},
                **{f"policy/{k}": v for k, v in tree(generated / "policy").items()},
            }
            actual = {
                **{f"sample_cases/{k}": v for k, v in tree(PACKAGE / "sample_cases").items()},
                **{f"policy/{k}": v for k, v in tree(PACKAGE / "policy").items()},
            }
            if expected != actual:
                raise SystemExit("packaged cases and policy differ from repository sources")
        print("PASS: packaged cases and policy are byte-stable")
        return 0
    shutil.rmtree(PACKAGE / "sample_cases", ignore_errors=True)
    shutil.rmtree(PACKAGE / "policy", ignore_errors=True)
    copy_into(PACKAGE)
    print("PASS: synchronized package cases and policy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
