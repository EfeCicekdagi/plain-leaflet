"""İlaçlar arası etkileşim kontrolü (LLM'siz).

Şimdilik mock: mock/interactions_output.json dosyasını aynen döndürür.
Gerçek sürümde imza aynı kalacak.
"""

import json
from pathlib import Path

MOCK_PATH = Path(__file__).resolve().parent.parent / "mock" / "interactions_output.json"


def check_interactions(kt_metinleri: dict[str, str]) -> list[dict]:
    """{ilaç adı: KT metni} alır, uyarı listesi döndürür. Hata olursa []."""
    try:
        with open(MOCK_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []
