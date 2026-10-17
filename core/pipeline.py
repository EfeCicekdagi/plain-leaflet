"""analyze(): KT metni -> 5 sade kart, eczacıya sorular ve doğrulama sonucu.

Akış (Draft -> Validate -> Finalize):
  1. Taslak: Prompt 1 (prompts/01_kartlar.txt) kartları ve eczacı sorularını üretir.
  2. Kod kontrolü: her "kanit" gerçekten KT metninde geçiyor mu? (difflib, eşik config.KANIT_ESIK)
     Sayılar tutarlı mı? (kanıttaki sayılar KT'de, sade cümledeki sayılar kanıtta)
  3. LLM kontrolü: Prompt 2 (prompts/02_dogrulayici.txt) her sade cümleyi 4 kritere göre alıntısıyla karşılaştırır.
  4. Son hal: geçemeyen madde kartlardan çıkarılır, "desteklenmeyen" listesine yazılır, güven hesaplanır.
     Son kontrol insandadır: her madde kaynağıyla gösterilir, belirsizlikler eczacıya soru olarak verilir.
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


def _prompt_yukle(yol) -> tuple[str, str]:
    """Prompt dosyasını (sistem, talimat) olarak ikiye böler. Sistem: her çağrıda sabit kurallar. Talimat: bu çağrının görevi."""
    with open(yol, encoding="utf-8") as f:
        metin = f.read()
    sistem, talimat = metin.split("### TALİMAT", 1)
    return sistem.replace("### SİSTEM", "", 1).strip(), talimat.strip()


def _veri_temizle(metin: str) -> str:
    """Belge içinden sınır etiketlerini siler; belge kendi etiketini kapatıp talimat bölümüne sızamaz."""
    return re.sub(r"</?\s*(kullanma_talimati|maddeler)\s*>", " ", metin, flags=re.IGNORECASE)


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


def _ask_json(talimat: str, sistem: str, sema: dict, model: str | None = None) -> dict:
    """Doğrula -> onar -> tekrar doğrula: cevap geçerli JSON değilse bir kez daha, uyararak sorar."""
    try:
        return _json_coz(ask(talimat, sistem=sistem, sema=sema, model=model))
    except (json.JSONDecodeError, ValueError):
        onar = talimat + "\n\nÖNEMLİ: Önceki cevabın geçerli JSON değildi. Sadece şemaya uyan geçerli JSON döndür."
        return _json_coz(ask(onar, sistem=sistem, sema=sema, model=model))


# ---------- Kod kontrolü: kanıt KT metninde geçiyor mu? ----------

def turkce_kucuk(metin: str) -> str:
    return metin.replace("İ", "i").replace("I", "ı").lower()


def _sadelestir(metin: str) -> str:
    """Karşılaştırma için: Türkçe küçük harf, tek tip tırnak ve tire, PDF satır sonu tirelerini birleştir, boşlukları teke indir."""
    metin = unicodedata.normalize("NFC", metin)
    metin = turkce_kucuk(metin).replace("̇", "").replace("­", "")  # "i̇" (i + nokta) ve yumuşak tire
    metin = re.sub(r"[‘’`´]", "'", metin)
    metin = re.sub(r"[“”«»]", '"', metin)
    metin = re.sub(r"[‐‑–—]", "-", metin)
    metin = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", metin)
    return re.sub(r"\s+", " ", metin).strip()


def kanit_skoru(kanit: str, kt_metni: str) -> float:
    """Kanıtın KT metnindeki en benzer parçaya benzerliği (0-1). Birebir geçiyorsa 1.0."""
    k, m = _sadelestir(kanit), _sadelestir(kt_metni)
    if not k or not m:
        return 0.0
    if k in m:
        return 1.0

    # Aday başlangıç noktaları: en uzun ortak parça + kanıtın birkaç parçasının metinde birebir geçtiği yerler
    adaylar = set()
    eslesme = SequenceMatcher(None, m, k, autojunk=False).find_longest_match(0, len(m), 0, len(k))
    if eslesme.size:
        adaylar.add(eslesme.a - eslesme.b)
    parca = 12
    for ofset in range(0, max(1, len(k) - parca + 1), max(1, len(k) // 6)):
        bulunan = m.find(k[ofset:ofset + parca])
        for _ in range(5):
            if bulunan == -1:
                break
            adaylar.add(bulunan - ofset)
            bulunan = m.find(k[ofset:ofset + parca], bulunan + 1)

    en_iyi = 0.0
    for aday in adaylar:
        for kayma in (-6, -3, 0, 3, 6):
            for uzunluk in (len(k) - 6, len(k), len(k) + 6):
                bas = max(0, aday + kayma)
                sm = SequenceMatcher(None, m[bas:bas + max(1, uzunluk)], k, autojunk=False)
                if sm.real_quick_ratio() > en_iyi and sm.quick_ratio() > en_iyi:
                    en_iyi = max(en_iyi, sm.ratio())
    return en_iyi


_SAYI_KELIMELERI = {"bir": "1", "iki": "2", "üç": "3", "dört": "4", "beş": "5", "altı": "6", "yedi": "7",
                    "sekiz": "8", "dokuz": "9", "on": "10", "yarım": "0.5", "buçuk": "0.5"}


def _sayilar(metin: str, kelimeler_dahil: bool = False) -> set[str]:
    metin = _sadelestir(metin)
    sayilar = {s.replace(",", ".") for s in re.findall(r"\d+(?:[.,]\d+)?", metin)}
    if kelimeler_dahil:
        sayilar |= {_SAYI_KELIMELERI[k] for k in re.findall(r"[a-zçğıöşü]+", metin) if k in _SAYI_KELIMELERI}
    return sayilar


def sayilar_tutarli(metin: str, kanit: str, kt_metni: str) -> bool:
    """Kanıttaki her sayı KT'de, sade cümledeki her sayı kanıtta geçmeli. Doz/yaş/süre değişikliğini kodla yakalar."""
    return _sayilar(kanit) <= _sayilar(kt_metni) and _sayilar(metin) <= _sayilar(kanit, kelimeler_dahil=True)


# ---------- LLM kontrolü: sade cümle alıntıya sadık mı? ----------

def _llm_kontrol(maddeler: list[dict]) -> dict[int, dict] | None:
    """{id: sonuç} döndürür. Sonuçta 4 kriter ve "destekleniyor" var. Doğrulayıcı çağrısı başarısız olursa None."""
    if not maddeler:
        return {}
    sistem, talimat = _prompt_yukle(config.PROMPT_DOGRULAYICI)
    girdi = _veri_temizle(json.dumps(maddeler, ensure_ascii=False, indent=1))
    try:
        sonuclar = _ask_json(talimat.replace("{maddeler}", girdi), sistem, schema.DOGRULAYICI_CEVAP_SEMASI,
                             model=config.DOGRULAYICI_MODEL).get("sonuclar", [])
    except Exception:
        return None
    kararlar = {}
    for s in sonuclar if isinstance(sonuclar, list) else []:
        if not isinstance(s, dict) or not isinstance(s.get("id"), int):
            continue
        kriterler = {k: s.get(k) for k in schema.DOGRULAYICI_KRITERLER}
        if not isinstance(s.get("destekleniyor"), bool) or not all(isinstance(v, bool) for v in kriterler.values()):
            continue
        # Model "destekleniyor" dese bile bir kriter hayır ise madde reddedilir (karar kodda verilir)
        kararlar[s["id"]] = {**kriterler, "destekleniyor": s["destekleniyor"] and all(kriterler.values())}
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


def dogrula(sonuc: dict, kt_metni: str) -> tuple[dict, dict]:
    """İki katmanlı kontrol. Geçemeyen maddeleri kartlardan çıkarır, guven'i hesaplar. (sonuc, detay) döndürür."""
    desteklenmeyen = list(sonuc["dogrulama"]["desteklenmeyen"])
    detay = {"kod_elenen": 0, "sayi_elenen": 0, "llm_elenen": 0, "kriter_ret": {k: 0 for k in schema.DOGRULAYICI_KRITERLER}}

    # 1) Kod kontrolü
    adaylar = []  # (kart, madde)
    for kart in schema.KARTLAR:
        for madde in sonuc["kartlar"][kart]:
            if not madde["kanit"] or kanit_skoru(madde["kanit"], kt_metni) < config.KANIT_ESIK:
                detay["kod_elenen"] += 1
            elif not sayilar_tutarli(madde["metin"], madde["kanit"], kt_metni):
                detay["sayi_elenen"] += 1
            else:
                adaylar.append((kart, madde))
                continue
            desteklenmeyen.append(madde["metin"])

    # 2) LLM kontrolü (sadece kod kontrolünü geçenler)
    kararlar = _llm_kontrol([{"id": i, "metin": m["metin"], "kanit": m["kanit"]} for i, (_, m) in enumerate(adaylar)])
    dogrulayici_tam = kararlar is not None and len(kararlar) == len(adaylar)
    detay["dogrulayici_calisti"] = kararlar is not None

    kartlar = {kart: [] for kart in schema.KARTLAR}
    for i, (kart, madde) in enumerate(adaylar):
        karar = (kararlar or {}).get(i)
        # Doğrulayıcı çalışmadıysa veya bu maddeye cevap vermediyse madde kalır, güven düşürülür
        if karar is not None and not karar["destekleniyor"]:
            desteklenmeyen.append(madde["metin"])
            detay["llm_elenen"] += 1
            for k in schema.DOGRULAYICI_KRITERLER:
                detay["kriter_ret"][k] += not karar[k]
        else:
            kartlar[kart].append(madde)

    sonuc["kartlar"] = kartlar
    kalan = schema.madde_sayisi(sonuc)
    sonuc["dogrulama"] = {
        "desteklenmeyen": desteklenmeyen,
        "guven": _guven(kalan, detay["kod_elenen"] + detay["sayi_elenen"] + detay["llm_elenen"], dogrulayici_tam),
    }
    return sonuc, detay


# ---------- Ana fonksiyon ----------

def analiz_detayli(kt_metni: str) -> tuple[dict, dict]:
    """analyze() ile aynı sonucu ve ölçüm için ara bilgileri döndürür. Hiçbir zaman hata fırlatmaz."""
    if config.USE_MOCK:
        return _mock(), {}

    try:
        if not isinstance(kt_metni, str) or len(kt_metni.strip()) < config.MIN_KT_KARAKTER:
            return schema.hata("Metin çok kısa. Lütfen ilacın kutusundan çıkan kullanma talimatını yükleyin veya yapıştırın."), {}
        kt_metni = kt_metni.strip()[:config.MAX_KT_KARAKTER]

        sistem, talimat = _prompt_yukle(config.PROMPT_KARTLAR)
        ham = _ask_json(talimat.replace("{kt_metni}", _veri_temizle(kt_metni)), sistem, schema.KART_CEVAP_SEMASI)

        analiz = ham.get("analiz") if isinstance(ham.get("analiz"), dict) else {}
        detay = {
            "uyari_sayisi": len(analiz.get("uyarilar") or []),
            "belirsiz_sayisi": len(analiz.get("belirsiz_noktalar") or []),
            "soru_adayi_sayisi": len(analiz.get("soru_adaylari") or []),
        }
        if analiz.get("kt_mi") is False:
            return schema.hata("Bu metin bir ilaç kullanma talimatına benzemiyor. Lütfen ilacın kutusundan çıkan "
                               "kullanma talimatını yükleyin."), {**detay, "red_nedeni": analiz.get("red_nedeni", "")}

        sonuc = schema.normalize(ham)
        detay["taslak_madde"] = schema.madde_sayisi(sonuc)
        if detay["taslak_madde"] == 0:
            return schema.hata("Talimattan sade bilgi çıkarılamadı. Lütfen eczacınıza danışın."), detay

        sonuc, dogrulama_detay = dogrula(sonuc, kt_metni)
        return sonuc, {**detay, **dogrulama_detay}
    except Exception as e:
        return schema.hata(f"Analiz yapılamadı ({e}). Lütfen biraz sonra tekrar deneyin."), {}


def analyze(kt_metni: str) -> dict:
    return analiz_detayli(kt_metni)[0]
