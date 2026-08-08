#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def main() -> int:
    failures: list[str] = []
    count = 0
    for markdown in sorted(ROOT.rglob("*.md")):
        if any(part in {".git", ".venv", "build", "dist"} for part in markdown.parts):
            continue
        text = markdown.read_text(encoding="utf-8")
        for target in LINK.findall(text):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            relative = target.split("#", 1)[0]
            if not relative:
                continue
            candidate = (markdown.parent / relative).resolve()
            count += 1
            if ROOT.resolve() not in candidate.parents and candidate != ROOT.resolve():
                failures.append(
                    f"link escapes repository: {markdown.relative_to(ROOT)} -> {target}"
                )
            elif not candidate.exists():
                failures.append(f"missing link target: {markdown.relative_to(ROOT)} -> {target}")
    if failures:
        raise SystemExit("\n".join(failures))
    print(f"PASS: {count} repository-relative Markdown links resolve")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
