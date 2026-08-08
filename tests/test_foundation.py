from pathlib import Path

from go_live_decision_agent.canonical import canonical_json_bytes, sha256_bytes
from go_live_decision_agent.errors import SecurityBoundaryError
from go_live_decision_agent.paths import safe_child, validate_identifier


def test_canonical_json_is_stable() -> None:
    assert canonical_json_bytes({"b": 2, "a": 1}) == b'{"a":1,"b":2}'


def test_sha256_is_stable() -> None:
    assert (
        sha256_bytes(b"go-live")
        == "f3ca808e77fbc2520ff76992f5ed47cdccbbc3fc52e2c0fe06cd54c468e2a9fe"
    )


def test_identifier_accepts_bounded_value() -> None:
    assert validate_identifier("RUN-001") == "RUN-001"


def test_identifier_rejects_path_traversal() -> None:
    try:
        validate_identifier("../escape")
    except SecurityBoundaryError:
        pass
    else:
        raise AssertionError("path traversal should be rejected")


def test_safe_child_stays_under_root(tmp_path: Path) -> None:
    assert safe_child(tmp_path, "packet-1").parent == tmp_path.resolve()
