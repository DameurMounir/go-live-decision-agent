#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".py", ".md", ".toml", ".yml", ".yaml", ".json", ".txt", ".svg", ".html"}
FORBIDDEN_NAMES = {".env", "id_rsa", "id_ed25519"}
PRIVATE_MARKERS = [
    re.compile(r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
]


def main() -> int:
    findings: list[str] = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        if any(
            part
            in {".git", ".venv", "build", "dist", ".mypy_cache", ".pytest_cache", ".ruff_cache"}
            for part in path.parts
        ):
            continue
        relative = path.relative_to(ROOT).as_posix()
        if path.name in FORBIDDEN_NAMES or path.suffix.lower() in {
            ".pem",
            ".key",
            ".p12",
            ".sqlite3",
        }:
            findings.append(f"forbidden file: {relative}")
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="strict")
        for pattern in PRIVATE_MARKERS:
            if pattern.search(text):
                findings.append(f"secret-like material in {relative}")
    if findings:
        raise SystemExit("\n".join(findings))
    print("PASS: synthetic public boundary and high-confidence secret patterns verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
