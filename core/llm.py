"""Modele giden tek kapı. Projede Gemini'ye sadece buradan gidilir.

API testi:  python -m core.llm
"""
import os
import time

from google import genai
from google.genai import errors, types

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


def _uret(model: str, contents, ayar: types.GenerateContentConfig) -> str:
    """Tek çağrı. Hata olursa config.LLM_RETRY kez tekrar dener; kota hatasında (429) daha uzun bekler."""
    son_hata = None
    for deneme in range(1 + config.LLM_RETRY):
        try:
            cevap = _istemci().models.generate_content(model=model, contents=contents, config=ayar)
            if cevap.text:
                return cevap.text
            son_hata = "modelden boş cevap geldi"
            bekle = config.LLM_RETRY_WAIT
        except errors.ClientError as e:
            if e.code != 429:
                raise  # 400/403/404 tekrar denemekle düzelmez
            son_hata = "kota doldu (429), biraz sonra tekrar deneyin"
            bekle = config.LLM_KOTA_WAIT
        except errors.APIError as e:
            son_hata = f"{e.code} {e.status}"
            bekle = config.LLM_RETRY_WAIT
        if deneme < config.LLM_RETRY:
            time.sleep(bekle)
    raise RuntimeError(f"Model çağrısı başarısız: {son_hata}")


def ask(prompt: str, sistem: str | None = None, sema: dict | None = None, model: str | None = None,
        dusunme: int | None = None) -> str:
    """Prompt'u modele gönderir, JSON metni döndürür. Başarısız olursa RuntimeError.

    sistem: her çağrıda sabit kurallar (system instruction). prompt: bu çağrının görevi.
    sema: cevabın uyması gereken JSON şeması (schema-first). Model şemayı reddederse şemasız tekrar denenir.
    dusunme: modelin gizli düşünme bütçesi (token). None = model varsayılanı, 0 = kapalı (hızlı).
    """
    model = model or config.MODEL_NAME
    ayar = types.GenerateContentConfig(
        temperature=config.TEMPERATURE,  # 0 = greedy decoding, her seferinde aynı ve en olası cevap
        response_mime_type="application/json",
        system_instruction=sistem,
        response_schema=types.Schema.model_validate(sema) if sema else None,
        thinking_config=types.ThinkingConfig(thinking_budget=dusunme) if dusunme is not None else None,
    )
    try:
        return _uret(model, prompt, ayar)
    except errors.ClientError as e:
        if e.code == 400 and (sema is not None or dusunme is not None):
            return ask(prompt, sistem, None, model)  # model şemayı veya düşünme ayarını desteklemiyor
        if e.code == 404 and model != config.MODEL_NAME:
            return ask(prompt, sistem, sema, config.MODEL_NAME, dusunme)
        raise RuntimeError(f"Model çağrısı başarısız: {e.code} {e.message}") from e


def ask_image(prompt: str, gorsel: bytes, mime_type: str = "image/jpeg") -> str:
    """Görsel + prompt -> düz metin. Fotoğraftan KT okumak (image_to_text) için. Başarısız olursa RuntimeError."""
    ayar = types.GenerateContentConfig(temperature=config.TEMPERATURE)
    icerik = [types.Part.from_bytes(data=gorsel, mime_type=mime_type), prompt]
    try:
        return _uret(config.MODEL_NAME, icerik, ayar)
    except errors.ClientError as e:
        raise RuntimeError(f"Model çağrısı başarısız: {e.code} {e.message}") from e


if __name__ == "__main__":
    print(f"Model: {config.MODEL_NAME}")
    try:
        print(ask('Sadece şu JSON\'u döndür: {"durum": "tamam"}'))
    except RuntimeError as e:
        print(f"HATA: {e}")
