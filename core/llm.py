"""Modele giden tek kapı. Projede Gemini'ye sadece buradan gidilir.

API testi:  python -m core.llm
"""
import os
import sys
import time

from google import genai
from google.genai import errors, types

import config

_client = None


class KotaHatasi(RuntimeError):
    """Ücretsiz kota doldu (429). Arayüz kullanıcıya "daha sonra tekrar deneyin" der."""


def _istemci() -> genai.Client:
    global _client
    if _client is None:
        anahtar = os.getenv("GEMINI_API_KEY", "").strip()
        if not anahtar:
            raise RuntimeError("GEMINI_API_KEY bulunamadı. .env.example dosyasını .env olarak kopyalayıp anahtarı yazın.")
        _client = genai.Client(api_key=anahtar)
    return _client


def _uret(model: str, contents, ayar: types.GenerateContentConfig) -> str:
    """_uret_tek; ana model yoğunluk/kota yüzünden başarısız olursa config.YEDEK_MODEL ile bir kez daha."""
    try:
        return _uret_tek(model, contents, ayar)
    except RuntimeError:
        yedek = config.YEDEK_MODEL
        if not yedek or yedek == model or not os.getenv("GEMINI_API_KEY", "").strip():
            raise
        print(f"[llm] {model} başarısız, yedek model deneniyor: {yedek}", file=sys.stderr)
        return _uret_tek(yedek, contents, ayar)


def _uret_tek(model: str, contents, ayar: types.GenerateContentConfig) -> str:
    """Tek çağrı. Hata olursa config.LLM_RETRY kez tekrar dener; kota hatasında (429) daha uzun bekler."""
    istemci = _istemci()  # anahtar yoksa tekrar denemeden hemen hata
    son_hata, kota = None, False
    for deneme in range(1 + config.LLM_RETRY):
        try:
            cevap = istemci.models.generate_content(model=model, contents=contents, config=ayar)
            if cevap.text:
                return cevap.text
            son_hata, kota = "modelden boş cevap geldi", False
            bekle = config.LLM_RETRY_WAIT
        except errors.ClientError as e:
            if e.code != 429:
                raise  # 400/403/404 tekrar denemekle düzelmez
            son_hata, kota = "kota doldu (429), biraz sonra tekrar deneyin", True
            bekle = config.LLM_KOTA_WAIT
        except errors.APIError as e:
            son_hata, kota = f"{e.code} {e.status}", False
            bekle = config.LLM_RETRY_WAIT
        except Exception as e:  # ağ kopması, zaman aşımı
            son_hata, kota = f"{type(e).__name__}: {e}", False
            bekle = config.LLM_RETRY_WAIT
        if deneme < config.LLM_RETRY:
            time.sleep(bekle)
    raise (KotaHatasi if kota else RuntimeError)(f"Model çağrısı başarısız: {son_hata}")


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
        max_output_tokens=config.MAX_CIKTI_TOKEN,  # model döngüye girerse sonsuza kadar beklemesin
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
