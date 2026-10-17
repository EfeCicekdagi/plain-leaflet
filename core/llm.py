"""Modele giden tek kapı. Projede Gemini'ye sadece buradan gidilir.

API testi:  python -m core.llm
"""
import os
import time

from google import genai
from google.genai import types

import config

_client = None


def _istemci() -> genai.Client:
    global _client
    if _client is None:
        anahtar = os.getenv("GEMINI_API_KEY", "").strip()
        if not anahtar:
            raise RuntimeError("GEMINI_API_KEY bulunamadı. .env.example dosyasını .env olarak kopyalayıp anahtarı yazın.")
        _client = genai.Client(api_key=anahtar)
    return _client


def ask(prompt: str) -> str:
    """Prompt'u modele gönderir, JSON metni döndürür. Hata olursa 1 kez tekrar dener, yine olmazsa RuntimeError."""
    ayar = types.GenerateContentConfig(
        temperature=config.TEMPERATURE,
        response_mime_type="application/json",
    )
    son_hata = None
    for deneme in range(1 + config.LLM_RETRY):
        try:
            cevap = _istemci().models.generate_content(model=config.MODEL_NAME, contents=prompt, config=ayar)
            if cevap.text:
                return cevap.text
            son_hata = "modelden boş cevap geldi"
        except RuntimeError:
            raise
        except Exception as e:
            son_hata = f"{type(e).__name__}: {e}"
        if deneme < config.LLM_RETRY:
            time.sleep(config.LLM_RETRY_WAIT)
    raise RuntimeError(f"Model çağrısı başarısız ({son_hata})")


if __name__ == "__main__":
    print(f"Model: {config.MODEL_NAME}")
    print(ask('Sadece şu JSON\'u döndür: {"durum": "tamam"}'))
