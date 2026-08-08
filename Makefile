.PHONY: sync test gate ui

sync:
	uv sync --all-extras --group dev

test:
	uv run pytest -q

gate:
	uv run python scripts/ci_gate.py

ui:
	uv run streamlit run streamlit_app.py
