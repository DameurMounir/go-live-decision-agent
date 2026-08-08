from __future__ import annotations

import re
from importlib.resources import files
from pathlib import Path

from .errors import SecurityBoundaryError

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


def validate_identifier(value: str, *, field: str = "identifier") -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise SecurityBoundaryError(f"invalid {field}: {value!r}")
    return value


def safe_child(root: Path, name: str) -> Path:
    validate_identifier(name, field="path component")
    root = root.resolve()
    target = (root / name).resolve()
    if target.parent != root:
        raise SecurityBoundaryError(f"path escapes root: {target}")
    return target


def packaged_policy_dir() -> Path:
    return Path(str(files("go_live_decision_agent").joinpath("policy")))


def packaged_cases_dir() -> Path:
    return Path(str(files("go_live_decision_agent").joinpath("sample_cases")))
