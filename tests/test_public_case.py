from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_readme_contains_three_decisions() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "**PASS**" in text
    assert "**BLOCKED**" in text
    assert "**FAIL**" in text


def test_readme_preserves_human_authority() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "does **not** deploy" in text
    assert "human release authority" in text.lower()


def test_public_assets_exist() -> None:
    assert {path.name for path in (ROOT / "assets").glob("*.svg")} == {
        "decision-precedence.svg",
        "gate-map.svg",
        "interface-preview.svg",
        "social-preview.svg",
        "workflow.svg",
    }


def test_public_claim_verifier_passes() -> None:
    from scripts.verify_public_claims import main

    assert main() == 0
