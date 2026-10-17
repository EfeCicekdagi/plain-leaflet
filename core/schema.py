"""analyze() çıktısının veri sözleşmesi. Sadece Kişi 1 değiştirir.

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

GUVEN_DEGERLERI = ("yuksek", "orta", "dusuk")


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
            if metin:
                sonuc["kartlar"][kart].append({"metin": metin, "kanit": kanit})

    sorular = ham.get("eczaciya_sorular") if isinstance(ham.get("eczaciya_sorular"), list) else []
    sonuc["eczaciya_sorular"] = [_yazi(s) for s in sorular if _yazi(s)]

    dogrulama = ham.get("dogrulama") if isinstance(ham.get("dogrulama"), dict) else {}
    desteklenmeyen = dogrulama.get("desteklenmeyen") if isinstance(dogrulama.get("desteklenmeyen"), list) else []
    sonuc["dogrulama"]["desteklenmeyen"] = [_yazi(d) for d in desteklenmeyen if _yazi(d)]
    if dogrulama.get("guven") in GUVEN_DEGERLERI:
        sonuc["dogrulama"]["guven"] = dogrulama["guven"]

    return sonuc


def madde_sayisi(sonuc: dict) -> int:
    return sum(len(sonuc.get("kartlar", {}).get(kart, [])) for kart in KARTLAR)
