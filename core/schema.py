"""analyze() çıktısının veri sözleşmesi. Sadece Kişi 1 değiştirir.

Kartlar KT ile aynı dildedir (Türkçe veya İngilizce). JSON anahtarları her zaman aynıdır.

{
  "ilac_adi": "ÖRNEKİLAÇ 500 mg tablet",
  "kartlar": {
    "ne_icin":          [{"metin": "...", "kanit": "KT'den birebir alıntı"}],
    "nasil_kullanilir": [...],
    "hemen_doktora":    [...],
    "yan_etkiler":      [...],
    "saklama":          [...]
  },
  "eczaciya_sorular": ["...", "..."],
  "dogrulama": {
    "desteklenmeyen": ["Kaynağı bulunamadığı için çıkarılan madde"],
    "guven": "yuksek | orta | dusuk"
  }
}

Hata olursa sadece {"hata": "açıklama"} döner.
"""

# Kartların sırası arayüzdeki sırayla aynıdır
KARTLAR = ("ne_icin", "nasil_kullanilir", "hemen_doktora", "yan_etkiler", "saklama")

KART_BASLIKLARI = {
    "ne_icin": "Ne için kullanılır?",
    "nasil_kullanilir": "Nasıl kullanılır?",
    "hemen_doktora": "Hemen doktora başvurun",
    "yan_etkiler": "Olası yan etkiler",
    "saklama": "Nasıl saklanır?",
}

# Arayüz İngilizce: kart başlıkları
KART_BASLIKLARI_EN = {
    "ne_icin": "What is it for?",
    "nasil_kullanilir": "How do I take it?",
    "hemen_doktora": "See a doctor right away if",
    "yan_etkiler": "Possible side effects",
    "saklama": "How do I store it?",
}

GUVEN_DEGERLERI = ("yuksek", "orta", "dusuk")

MAX_MADDE = 5  # kart başına en fazla madde
MAX_SORU = 5   # en fazla eczacı sorusu


def bos_sonuc(ilac_adi: str = "") -> dict:
    return {
        "ilac_adi": ilac_adi,
        "kartlar": {kart: [] for kart in KARTLAR},
        "eczaciya_sorular": [],
        "dogrulama": {"desteklenmeyen": [], "guven": "dusuk"},
    }


def hata(aciklama: str) -> dict:
    return {"hata": aciklama}


def _yazi(deger) -> str:
    return deger.strip() if isinstance(deger, str) else ""


def normalize(ham: dict) -> dict:
    """Modelden gelen JSON'u sözleşmeye uydurur: eksik alanı doldurur, fazlasını atar."""
    sonuc = bos_sonuc(_yazi(ham.get("ilac_adi")))

    kartlar = ham.get("kartlar") if isinstance(ham.get("kartlar"), dict) else {}
    for kart in KARTLAR:
        maddeler = kartlar.get(kart) if isinstance(kartlar.get(kart), list) else []
        for madde in maddeler:
            if not isinstance(madde, dict):
                continue
            metin, kanit = _yazi(madde.get("metin")), _yazi(madde.get("kanit"))
            if metin and len(sonuc["kartlar"][kart]) < MAX_MADDE:
                sonuc["kartlar"][kart].append({"metin": metin, "kanit": kanit})

    sorular = ham.get("eczaciya_sorular") if isinstance(ham.get("eczaciya_sorular"), list) else []
    sonuc["eczaciya_sorular"] = [_yazi(s) for s in sorular if _yazi(s)][:MAX_SORU]

    dogrulama = ham.get("dogrulama") if isinstance(ham.get("dogrulama"), dict) else {}
    desteklenmeyen = dogrulama.get("desteklenmeyen") if isinstance(dogrulama.get("desteklenmeyen"), list) else []
    sonuc["dogrulama"]["desteklenmeyen"] = [_yazi(d) for d in desteklenmeyen if _yazi(d)]
    if dogrulama.get("guven") in GUVEN_DEGERLERI:
        sonuc["dogrulama"]["guven"] = dogrulama["guven"]

    return sonuc


def madde_sayisi(sonuc: dict) -> int:
    return sum(len(sonuc.get("kartlar", {}).get(kart, [])) for kart in KARTLAR)


# ---------- Modelin cevap şemaları (Gemini response_schema, schema-first) ----------
# Alan sırası (property_ordering) önemlidir: model önce "analiz" alanını (adım adım düşünme) yazar, sonra kartları.

def _nesne(alanlar: dict, sira: list[str]) -> dict:
    return {"type": "OBJECT", "properties": alanlar, "required": sira, "property_ordering": sira}


def _liste(oge: dict, en_fazla: int | None = None) -> dict:
    sema = {"type": "ARRAY", "items": oge}
    if en_fazla is not None:
        sema["max_items"] = en_fazla
    return sema


_YAZI = {"type": "STRING"}
_MADDE = _nesne({"metin": _YAZI, "kanit": _YAZI}, ["metin", "kanit"])

KART_CEVAP_SEMASI = _nesne(
    {
        "analiz": _nesne(
            {
                "kt_mi": {"type": "BOOLEAN"},
                "red_nedeni": _YAZI,
                "uyarilar": _liste(_YAZI),
                "belirsiz_noktalar": _liste(_YAZI),
                "soru_adaylari": _liste(_nesne(
                    {
                        "eksen": {"type": "STRING", "enum": ["doz_zaman", "diger_ilaclar_besinler", "yan_etki_takibi", "ozel_durumlar", "unutma_saklama"]},
                        "soru": _YAZI,
                        "onem": {"type": "STRING", "enum": list(GUVEN_DEGERLERI)},
                    },
                    ["eksen", "soru", "onem"],
                )),
            },
            ["kt_mi", "red_nedeni", "uyarilar", "belirsiz_noktalar", "soru_adaylari"],
        ),
        "ilac_adi": _YAZI,
        "kartlar": _nesne({kart: _liste(_MADDE, MAX_MADDE) for kart in KARTLAR}, list(KARTLAR)),
        "eczaciya_sorular": _liste(_YAZI, MAX_SORU),
    },
    ["analiz", "ilac_adi", "kartlar", "eczaciya_sorular"],
)

DOGRULAYICI_KRITERLER = ("k1_ek_bilgi_yok", "k2_anlam_ayni", "k3_kosul_korunmus", "k4_sayilar_ayni")

DOGRULAYICI_CEVAP_SEMASI = _nesne(
    {
        "sonuclar": _liste(_nesne(
            {"id": {"type": "INTEGER"}, "neden": _YAZI, **{k: {"type": "BOOLEAN"} for k in DOGRULAYICI_KRITERLER}, "destekleniyor": {"type": "BOOLEAN"}},
            ["id", "neden", *DOGRULAYICI_KRITERLER, "destekleniyor"],
        )),
    },
    ["sonuclar"],
)

DUZELTME_CEVAP_SEMASI = _nesne(
    {"duzeltmeler": _liste(_nesne({"id": {"type": "INTEGER"}, "metin": _YAZI}, ["id", "metin"]))},
    ["duzeltmeler"],
)
