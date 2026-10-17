"""analyze(): KT metni -> 5 sade kart. Şimdilik mock döndürür."""
import json

import config


def analyze(kt_metni: str) -> dict:
    with open(config.MOCK_ANALYZE, encoding="utf-8") as f:
        return json.load(f)
