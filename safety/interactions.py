"""Rule-based drug interaction check (no LLM).

Currently a mock: returns mock/interactions_output.json as is.
The signature stays the same in the real implementation.
"""

import json
from pathlib import Path

MOCK_PATH = Path(__file__).resolve().parent.parent / "mock" / "interactions_output.json"


def check_interactions(leaflets: dict[str, str]) -> list[dict]:
    """Take {drug name: leaflet text} and return a list of warnings. Returns [] on error."""
    try:
        with open(MOCK_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []
