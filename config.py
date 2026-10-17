"""Ortak ayarlar. Sadece Kişi 1 değiştirir; diğer dosyalar ayarları buradan okur."""
import os
from pathlib import Path

from dotenv import load_dotenv

KOK = Path(__file__).resolve().parent
load_dotenv(KOK / ".env")

# Model
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
# Doğrulayıcı için ayrı model seçilebilir (örn. daha ucuz/hızlı gemini-2.5-flash-lite). Bulunamazsa MODEL_NAME kullanılır.
DOGRULAYICI_MODEL = os.getenv("GEMINI_DOGRULAYICI_MODEL", MODEL_NAME)
TEMPERATURE = 0.0      # greedy decoding: tıbbi metinde yaratıcılık değil tutarlılık istenir
LLM_RETRY = 1          # hata olursa kaç kez daha denenir
LLM_RETRY_WAIT = 3.0   # tekrar denemeden önce beklenecek saniye
LLM_KOTA_WAIT = 20.0   # kota hatasında (429) beklenecek saniye

# 1 ise analyze() modeli çağırmaz, mock JSON'u döndürür
USE_MOCK = os.getenv("USE_MOCK", "0") == "1"

# Dosya yolları
PROMPT_KARTLAR = KOK / "prompts" / "01_kartlar.txt"
PROMPT_DOGRULAYICI = KOK / "prompts" / "02_dogrulayici.txt"
MOCK_ANALYZE = KOK / "mock" / "analyze_output.json"

# Doğrulayıcı
KANIT_ESIK = 0.85       # difflib benzerliği bu eşiğin altındaysa kanıt KT'de yok sayılır
MAX_KT_KARAKTER = 60000  # daha uzun metinler kırpılır (KT'ler genelde 15-40 bin karakter)
MIN_KT_KARAKTER = 200    # daha kısa metin KT sayılmaz
