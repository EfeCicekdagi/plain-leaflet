"""Ortak ayarlar. Sadece Kişi 1 değiştirir; diğer dosyalar ayarları buradan okur."""
import os
from pathlib import Path

from dotenv import load_dotenv

KOK = Path(__file__).resolve().parent
load_dotenv(KOK / ".env")

# Model
# gemini-3.8-flash 17 Ekim'de yoğunluktan dolayı tek çağrıda 77-151 sn bekletti; 3.6-flash aynı KT'yi 21 sn'de, daha yüksek güvenle işledi
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
# Ana model 503 (yoğunluk) veya 429 (kota) ile başarısız olursa aynı çağrı bu modelle bir kez daha denenir.
# Ücretsiz kota model başına ayrı olduğu için kota dolunca da işe yarar. Boş bırakılırsa kapalı.
YEDEK_MODEL = os.getenv("GEMINI_YEDEK_MODEL", "gemini-3.5-flash").strip()
# Doğrulayıcı için ayrı model seçilebilir (örn. daha ucuz/hızlı gemini-3.5-flash-lite). Bulunamazsa MODEL_NAME kullanılır.
DOGRULAYICI_MODEL = os.getenv("GEMINI_DOGRULAYICI_MODEL", MODEL_NAME)
TEMPERATURE = 0.0      # greedy decoding: tıbbi metinde yaratıcılık değil tutarlılık istenir
# Modelin gizli düşünme bütçesi (token). Promptlarda açık adım adım düşünme (analiz/neden alanları) olduğu için kapalı:
# paracetamol KT'sinde taslak 40-69 sn'den 14 sn'ye indi, madde sayısı ve kanıt kontrolü sonucu değişmedi. None = model varsayılanı.
_dusunme = os.getenv("GEMINI_DUSUNME", "0").strip().lower()
DUSUNME_BUTCESI = int(_dusunme) if _dusunme.isdigit() else None
MAX_CIKTI_TOKEN = 16384  # gerçek çıktılar 3-6 bin token; sınır sadece döngüye giren cevabı keser
LLM_RETRY = 1          # hata olursa kaç kez daha denenir
LLM_RETRY_WAIT = 3.0   # tekrar denemeden önce beklenecek saniye
LLM_KOTA_WAIT = 20.0   # kota hatasında (429) beklenecek saniye

# 1 ise analyze() modeli çağırmaz, mock JSON'u döndürür
USE_MOCK = os.getenv("USE_MOCK", "0") == "1"

# Dosya yolları
PROMPT_KARTLAR = KOK / "prompts" / "01_kartlar.txt"
PROMPT_DOGRULAYICI = KOK / "prompts" / "02_dogrulayici.txt"
PROMPT_DUZELTME = KOK / "prompts" / "03_duzeltme.txt"
MOCK_ANALYZE = KOK / "mock" / "analyze_output.json"

# Doğrulayıcı
DUZELTME_ACIK = True    # doğrulayıcının reddettiği maddeler bir kez düzeltilip tekrar doğrulanır (Finalize adımı)
KANIT_ESIK = 0.95       # difflib benzerliği (boşluksuz) bu eşiğin altındaysa kanıt KT'de yok sayılır. Gerçek çıktılarda kanıtların hepsi 1.0 aldı; 0.95 tek harflik farkı kabul eder, kelime değişikliğini reddeder
MAX_KT_KARAKTER = 60000  # daha uzun metinler kırpılır (KT'ler genelde 15-40 bin karakter)
MIN_KT_KARAKTER = 200    # daha kısa metin KT sayılmaz
