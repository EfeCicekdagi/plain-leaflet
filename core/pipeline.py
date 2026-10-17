"""analyze(): KT metni -> 5 sade kart, eczacıya sorular ve doğrulama sonucu.

Akış:
  1. Prompt 1 (prompts/01_kartlar.txt) kartları üretir.
  2. Kod kontrolü: her "kanit" gerçekten KT metninde geçiyor mu? (difflib, eşik config.KANIT_ESIK)
  3. LLM kontrolü (prompts/02_dogrulayici.txt): sade cümle alıntıdan fazlasını söylüyor mu?
  Geçemeyen madde kartlardan çıkarılır, "desteklenmeyen" listesine yazılır.
"""
import json
import re
import unicodedata
from difflib import SequenceMatcher

import config
from core import schema
from core.llm import ask


def _mock() -> dict:
    with open(config.MOCK_ANALYZE, encoding="utf-8") as f:
        return json.load(f)


def _prompt_oku(yol) -> str:
    with open(yol, encoding="utf-8") as f:
        return f.read()


def _json_coz(cevap: str) -> dict:
    try:
        veri = json.loads(cevap)
    except json.JSONDecodeError:
        # Model JSON'un etrafına yazı eklediyse ilk { ile son } arasını dene
        bas, son = cevap.find("{"), cevap.rfind("}")
        if bas == -1 or son <= bas:
            raise
        veri = json.loads(cevap[bas:son + 1])
    if not isinstance(veri, dict):
        raise ValueError("model JSON nesnesi döndürmedi")
    return veri


# ---------- Kod kontrolü: kanıt KT metninde geçiyor mu? ----------

def turkce_kucuk(metin: str) -> str:
    return metin.replace("İ", "i").replace("I", "ı").lower()


def _sadelestir(metin: str) -> str:
    """Karşılaştırma için: Türkçe küçük harf, tek tip tırnak, PDF satır sonu tirelerini birleştir, boşlukları teke indir."""
    metin = unicodedata.normalize("NFC", metin)
    metin = turkce_kucuk(metin).replace("̇", "")  # PDF'ten gelen "i̇" (i + nokta)
    metin = re.sub(r"[‘’`´]", "'", metin)
    metin = re.sub(r"[“”«»]", '"', metin)
    metin = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", metin)
    return re.sub(r"\s+", " ", metin).strip()


def kanit_skoru(kanit: str, kt_metni: str) -> float:
    """Kanıtın KT metnindeki en benzer parçaya benzerliği (0-1). Birebir geçiyorsa 1.0."""
    k, m = _sadelestir(kanit), _sadelestir(kt_metni)
    if not k or not m:
        return 0.0
    if k in m:
        return 1.0
    eslesme = SequenceMatcher(None, m, k, autojunk=False).find_longest_match(0, len(m), 0, len(k))
    if eslesme.size == 0:
        return 0.0
    # En uzun ortak parçayı çapa alıp kanıt uzunluğunda pencereler dene
    bas = max(0, eslesme.a - eslesme.b)
    en_iyi = 0.0
    for kayma in (-10, -5, 0, 5, 10):
        for uzunluk in (len(k) - 10, len(k), len(k) + 10):
            b = max(0, bas + kayma)
            pencere = m[b:b + max(1, uzunluk)]
            en_iyi = max(en_iyi, SequenceMatcher(None, pencere, k, autojunk=False).ratio())
    return en_iyi


# ---------- LLM kontrolü: sade cümle alıntıya sadık mı? ----------

def _llm_kontrol(maddeler: list[dict]) -> dict[int, bool] | None:
    """{id: destekleniyor} döndürür. Doğrulayıcı çağrısı başarısız olursa None."""
    if not maddeler:
        return {}
    girdi = json.dumps(maddeler, ensure_ascii=False, indent=1)
    prompt = _prompt_oku(config.PROMPT_DOGRULAYICI).replace("{maddeler}", girdi)
    try:
        sonuclar = _json_coz(ask(prompt)).get("sonuclar", [])
    except Exception:
        return None
    kararlar = {}
    for s in sonuclar if isinstance(sonuclar, list) else []:
        if isinstance(s, dict) and isinstance(s.get("id"), int) and isinstance(s.get("destekleniyor"), bool):
            kararlar[s["id"]] = s["destekleniyor"]
    return kararlar


def _guven(kalan: int, cikarilan: int, dogrulayici_tam: bool) -> str:
    if kalan == 0:
        return "dusuk"
    oran = cikarilan / (kalan + cikarilan)
    if oran == 0 and dogrulayici_tam:
        return "yuksek"
    if oran <= 0.2:
        return "orta"
    return "dusuk"


def dogrula(sonuc: dict, kt_metni: str) -> dict:
    """İki katmanlı kontrol. Geçemeyen maddeleri kartlardan çıkarır, guven'i hesaplar."""
    desteklenmeyen = list(sonuc["dogrulama"]["desteklenmeyen"])

    # 1) Kod kontrolü
    adaylar = []  # (kart, madde)
    for kart in schema.KARTLAR:
        for madde in sonuc["kartlar"][kart]:
            if madde["kanit"] and kanit_skoru(madde["kanit"], kt_metni) >= config.KANIT_ESIK:
                adaylar.append((kart, madde))
            else:
                desteklenmeyen.append(madde["metin"])

    # 2) LLM kontrolü (sadece kod kontrolünü geçenler)
    girdi = [{"id": i, "metin": m["metin"], "kanit": m["kanit"]} for i, (_, m) in enumerate(adaylar)]
    kararlar = _llm_kontrol(girdi)
    dogrulayici_tam = kararlar is not None and len(kararlar) == len(adaylar)

    kartlar = {kart: [] for kart in schema.KARTLAR}
    for i, (kart, madde) in enumerate(adaylar):
        # Doğrulayıcı çalışmadıysa veya bu maddeye cevap vermediyse madde kalır, güven düşürülür
        if kararlar is not None and kararlar.get(i) is False:
            desteklenmeyen.append(madde["metin"])
        else:
            kartlar[kart].append(madde)

    sonuc["kartlar"] = kartlar
    kalan = schema.madde_sayisi(sonuc)
    cikarilan = len(desteklenmeyen) - len(sonuc["dogrulama"]["desteklenmeyen"])
    sonuc["dogrulama"] = {
        "desteklenmeyen": desteklenmeyen,
        "guven": _guven(kalan, cikarilan, dogrulayici_tam),
    }
    return sonuc


# ---------- Ana fonksiyon ----------

def analyze(kt_metni: str) -> dict:
    if config.USE_MOCK:
        return _mock()

    try:
        if not isinstance(kt_metni, str) or len(kt_metni.strip()) < config.MIN_KT_KARAKTER:
            return schema.hata("Metin çok kısa. Lütfen ilacın kullanma talimatını yükleyin veya yapıştırın.")
        kt_metni = kt_metni.strip()[:config.MAX_KT_KARAKTER]

        prompt = _prompt_oku(config.PROMPT_KARTLAR).replace("{kt_metni}", kt_metni)
        ham = _json_coz(ask(prompt))

        analiz = ham.get("analiz") if isinstance(ham.get("analiz"), dict) else {}
        if analiz.get("kt_mi") is False:
            return schema.hata("Bu metin bir ilaç kullanma talimatına benzemiyor.")

        sonuc = schema.normalize(ham)
        if schema.madde_sayisi(sonuc) == 0:
            return schema.hata("Talimattan sade bilgi çıkarılamadı. Lütfen eczacınıza danışın.")

        return dogrula(sonuc, kt_metni)
    except Exception as e:
        return schema.hata(f"Analiz yapılamadı: {e}")
