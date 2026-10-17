"""analyze(): KT metni -> 5 sade kart, eczacıya sorular ve doğrulama sonucu.

KT Türkçe veya İngilizce olabilir; kartlar KT ile aynı dilde üretilir, "kanit" her zaman KT'nin kendi dilindedir.

Akış (Draft -> Validate -> Finalize):
  1. Taslak: Prompt 1 (prompts/01_kartlar.txt) kartları ve eczacı sorularını üretir.
  2. Kod kontrolü: her "kanit" gerçekten KT metninde geçiyor mu? (difflib, eşik config.KANIT_ESIK)
     Sayılar tutarlı mı? (kanıttaki sayılar KT'de, sade cümledeki sayılar kanıtta)
  3. LLM kontrolü: Prompt 2 (prompts/02_dogrulayici.txt) her sade cümleyi 4 kritere göre alıntısıyla karşılaştırır.
  4. Düzeltme: LLM'in reddettiği maddeler gerekçesiyle bir kez yeniden yazılır (03_duzeltme.txt), 2. ve 3. adımdan tekrar geçer.
  5. Son hal: geçemeyen madde kartlardan çıkarılır, "desteklenmeyen" listesine yazılır, güven hesaplanır.
     Son kontrol insandadır: her madde kaynağıyla gösterilir, belirsizlikler eczacıya soru olarak verilir.
"""
import json
import re
import sys
import unicodedata
from difflib import SequenceMatcher
from functools import lru_cache

import config
from core import schema
from core.llm import KotaHatasi, ask


def _mock() -> dict:
    with open(config.MOCK_ANALYZE, encoding="utf-8") as f:
        return json.load(f)


# Kullanıcıya gösterilen mesajlar: KT'nin diline göre (dil anlaşılamazsa İngilizce, arayüz İngilizce)
MESAJLAR = {
    "kisa": {
        "tr": "Metin çok kısa. Lütfen ilacın kutusundan çıkan kullanma talimatını yükleyin veya yapıştırın.",
        "en": "The text is too short. Please upload or paste the patient leaflet that came with the medicine.",
    },
    "kt_degil": {
        "tr": "Bu metin bir ilaç kullanma talimatına benzemiyor. Lütfen ilacın kutusundan çıkan kullanma talimatını yükleyin.",
        "en": "This text does not look like a medicine leaflet. Please upload the patient leaflet that came with the medicine.",
    },
    "bos": {
        "tr": "Talimattan sade bilgi çıkarılamadı. Lütfen eczacınıza danışın.",
        "en": "No plain information could be taken from this leaflet. Please ask your pharmacist.",
    },
    "hata": {
        "tr": "Analiz yapılamadı. Lütfen biraz sonra tekrar deneyin.",
        "en": "The analysis could not be completed. Please try again in a moment.",
    },
    "kota": {
        "tr": "Yapay zekâ servisinin kullanım sınırı doldu. Lütfen daha sonra tekrar deneyin.",
        "en": "The AI service has reached its usage limit. Please try again later.",
    },
}

_TR_KELIMELER = {"ve", "bir", "bu", "ile", "için", "veya", "olan", "ilacı", "doktorunuza", "kullanmayınız", "gibi", "daha"}
_EN_KELIMELER = {"the", "and", "of", "to", "with", "your", "this", "you", "if", "or", "for", "medicine", "doctor", "take"}


def dil_tespit(metin: str) -> str:
    """"tr" veya "en". Türkçeye özgü harflere (ğ ş ı İ, büyük halleri dahil) ve sık geçen kelimelere bakar.
    Karar verilemezse "en" (arayüz İngilizce). Harfler küçültmeden önce sayılır: Türkçe kural ("I" -> "ı")
    İngilizcedeki "If"i Türkçe gösterir, normal kural da büyük harfli Türkçeden "İ"yi siler."""
    kelimeler = re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü]+", (metin or "")[:20000])
    tr = en = 0
    for k in kelimeler:
        kucuk = k.replace("İ", "i").lower()
        tr += (kucuk in _TR_KELIMELER) + 3 * any(h in k for h in "ğĞşŞıİ")
        en += kucuk in _EN_KELIMELER
    return "tr" if tr > en else "en"


DIL_ADLARI = {"tr": "Turkish", "en": "English"}


def _cikti_dili(ham: dict) -> str | None:
    """Modelin yazdığı sade cümlelerin dili. Cümle yoksa None."""
    kartlar = ham.get("kartlar") if isinstance(ham.get("kartlar"), dict) else {}
    metinler = [m.get("metin", "") for k in kartlar.values() if isinstance(k, list) for m in k if isinstance(m, dict)]
    metin = " ".join(x for x in metinler if isinstance(x, str))
    return dil_tespit(metin) if metin.strip() else None


def _mesaj(anahtar: str, dil: str) -> str:
    return MESAJLAR[anahtar][dil]


def _prompt_yukle(yol) -> tuple[str, str]:
    """Prompt dosyasını (sistem, talimat) olarak ikiye böler. Sistem: her çağrıda sabit kurallar. Talimat: bu çağrının görevi."""
    with open(yol, encoding="utf-8") as f:
        metin = f.read()
    sistem, talimat = metin.split("### INSTRUCTION", 1)
    return sistem.replace("### SYSTEM", "", 1).strip(), talimat.strip()


def _veri_temizle(metin: str) -> str:
    """Belge içinden sınır etiketlerini siler; belge kendi etiketini kapatıp talimat bölümüne sızamaz."""
    return re.sub(r"</?\s*(leaflet|items)\s*>", " ", metin, flags=re.IGNORECASE)


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
        return _json_coz(ask(talimat, sistem=sistem, sema=sema, model=model, dusunme=config.DUSUNME_BUTCESI))
    except (json.JSONDecodeError, ValueError):
        onar = talimat + "\n\nIMPORTANT: Your previous answer was not valid JSON. Return only valid JSON that matches the schema."
        return _json_coz(ask(onar, sistem=sistem, sema=sema, model=model, dusunme=config.DUSUNME_BUTCESI))


# ---------- Kod kontrolü: kanıt KT metninde geçiyor mu? ----------

def turkce_kucuk(metin: str) -> str:
    return metin.replace("İ", "i").replace("I", "ı").lower()


def _sadelestir(metin: str) -> str:
    """Karşılaştırma için: Türkçe küçük harf, tek tip tırnak ve tire, PDF satır sonu tirelerini birleştir, boşlukları teke indir."""
    metin = unicodedata.normalize("NFKC", metin)  # PDF ligatürleri: "ﬂ" -> "fl"
    metin = turkce_kucuk(metin).replace("̇", "").replace("­", "")  # "i̇" (i + nokta) ve yumuşak tire
    metin = re.sub(r"[‘’`´]", "'", metin)
    metin = re.sub(r"[“”«»]", '"', metin)
    metin = re.sub(r"[‐‑–—]", "-", metin)
    metin = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", metin)
    return re.sub(r"\s+", " ", metin).strip()


@lru_cache(maxsize=8)
def _kt_hazirla(kt_metni: str) -> str:
    """KT'nin karşılaştırmaya hazır, boşluksuz hali. Her madde için yeniden hesaplanmasın diye önbellekte tutulur."""
    return _sadelestir(kt_metni).replace(" ", "")


_KISA_PARCA = 40       # bundan kısa parçalarda bulanık eşleşme yanıltıcı olur, sadece birebir eşleşme kabul edilir
# " ... " ile birleştirilen parçalar KT'de sırayla ve bu kadar karakter (boşluksuz) içinde geçmeli: aynı bölüm.
# Gerçek çıktılarda en geniş yayılım 474 karakterdi; farklı bölümlerden toplanan parçalar bundan çok uzaktır.
_BOLUM_ARALIGI = 1000
_AYIRICI = r"\s*(?:\.\.\.|…|:|•)\s*"


def kanit_skoru(kanit: str, kt_metni: str) -> float:
    """Kanıtın KT metnindeki en benzer parçaya benzerliği (0-1). Birebir geçiyorsa 1.0.

    Kanıt " ... " (veya ":", "•") ile birleştirilmiş birkaç parçaysa (başlık ... liste maddesi):
    her parça ayrı aranır ve en düşük skor döner. Ayrıca parçalar KT'de sırayla ve birbirine yakın geçmelidir;
    farklı bölümlerden toplanmış parçalar (örn. saklama cümlesi ... doz cümlesi) 0 alır.
    ":" ile de bölünür: model başlık ile maddeyi ":" ile birleştirmiş olabilir; uzun gerçek bir başlığın
    arkasına eklenmiş kısa, uydurma bir parça da böylece ayrı yakalanır.
    Bilinen sınır: KT'de çok yerde geçen bir kelime ("Bulantı") yanlış başlığın altına bağlanırsa yakalanmayabilir.
    """
    parcalar = [p for p in re.split(_AYIRICI, kanit or "") if p.strip(" .:;,-•")]
    m = _kt_hazirla(kt_metni or "")
    if not parcalar or not m:
        return 0.0
    bulunanlar = [_parca_bul(p, m) for p in parcalar]
    skor = min(b[0] for b in bulunanlar)
    if len(bulunanlar) > 1 and skor > 0 and not _ayni_bolumde([b[1] for b in bulunanlar]):
        return 0.0
    return skor


def _ayni_bolumde(konumlar: list[list[int]]) -> bool:
    """Her parça için bir konum seçilebiliyor mu: artan sırada ve ilk ile son arası en fazla _BOLUM_ARALIGI?"""
    def ara(i: int, onceki: int, ilk: int) -> bool:
        if i == len(konumlar):
            return True
        return any(ara(i + 1, k, k if i == 0 else ilk) for k in konumlar[i]
                   if k >= onceki and (i == 0 or k - ilk <= _BOLUM_ARALIGI))
    return ara(0, -1, 0)


def _parca_bul(parca: str, m: str) -> tuple[float, list[int]]:
    """(benzerlik, KT'deki konumlar). m: _kt_hazirla() çıktısı."""
    k_bosluklu = _sadelestir(parca)
    k = k_bosluklu.replace(" ", "")  # boşluksuz: PDF'ten gelen bölünmüş kelimeler ("W ait", "K eep")
    if not k:
        return 0.0, []
    konumlar, bulunan = [], m.find(k)
    while bulunan != -1 and len(konumlar) < 30:
        konumlar.append(bulunan)
        bulunan = m.find(k, bulunan + 1)
    if konumlar:
        return 1.0, konumlar
    if len(k_bosluklu) < _KISA_PARCA:
        return 0.0, []

    # Bulanık karşılaştırma. Aday başlangıç noktaları: en uzun ortak parça + kanıtın birkaç parçasının birebir geçtiği yerler
    adaylar = set()
    eslesme = SequenceMatcher(None, m, k, autojunk=False).find_longest_match(0, len(m), 0, len(k))
    if eslesme.size:
        adaylar.add(eslesme.a - eslesme.b)
    parca_boyu = 12
    for ofset in range(0, max(1, len(k) - parca_boyu + 1), max(1, len(k) // 6)):
        bulunan = m.find(k[ofset:ofset + parca_boyu])
        for _ in range(5):
            if bulunan == -1:
                break
            adaylar.add(bulunan - ofset)
            bulunan = m.find(k[ofset:ofset + parca_boyu], bulunan + 1)

    en_iyi, en_iyi_konum = 0.0, 0
    for aday in adaylar:
        for kayma in (-6, -3, 0, 3, 6):
            for uzunluk in (len(k) - 6, len(k), len(k) + 6):
                bas = max(0, aday + kayma)
                sm = SequenceMatcher(None, m[bas:bas + max(1, uzunluk)], k, autojunk=False)
                if sm.real_quick_ratio() > en_iyi and sm.quick_ratio() > en_iyi:
                    oran = sm.ratio()
                    if oran > en_iyi:
                        en_iyi, en_iyi_konum = oran, bas
    return en_iyi, [en_iyi_konum]


_SAYI_KELIMELERI = {
    "bir": "1", "iki": "2", "üç": "3", "dört": "4", "beş": "5", "altı": "6", "yedi": "7", "sekiz": "8", "dokuz": "9",
    "on": "10", "yarım": "0.5", "buçuk": "0.5",
    "one": "1", "once": "1", "two": "2", "twice": "2", "three": "3", "four": "4", "five": "5", "six": "6",
    "seven": "7", "eight": "8", "nine": "9", "ten": "10", "half": "0.5",
}


def _sayilar(metin: str, kelimeler_dahil: bool = False) -> set[str]:
    metin = _sadelestir(metin)
    sayilar = {s.replace(",", ".") for s in re.findall(r"\d+(?:[.,]\d+)?", metin)}
    if kelimeler_dahil:
        sayilar |= {_SAYI_KELIMELERI[k] for k in re.findall(r"[a-zçğıöşü]+", metin) if k in _SAYI_KELIMELERI}
    return sayilar


@lru_cache(maxsize=8)
def _kt_sayilari(kt_metni: str) -> frozenset[str]:
    return frozenset(_sayilar(kt_metni))


def sayilar_tutarli(metin: str, kanit: str, kt_metni: str) -> bool:
    """Kanıttaki her sayı KT'de, sade cümledeki her sayı kanıtta geçmeli. Doz/yaş/süre değişikliğini kodla yakalar."""
    return _sayilar(kanit) <= _kt_sayilari(kt_metni) and _sayilar(metin) <= _sayilar(kanit, kelimeler_dahil=True)


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
        kararlar[s["id"]] = {**kriterler, "destekleniyor": s["destekleniyor"] and all(kriterler.values()),
                             "neden": s.get("neden", "")}
    return kararlar


def _guven(kalan: int, cikarilan: int, dogrulayici_tam: bool, dogrulayici_calisti: bool = True) -> str:
    # Hiçbir madde LLM doğrulayıcıdan geçmediyse güven düşüktür; arayüz "eczacınızla teyit edin" uyarısını gösterir
    if kalan == 0 or not dogrulayici_calisti:
        return "dusuk"
    oran = cikarilan / (kalan + cikarilan)
    if oran == 0 and dogrulayici_tam:
        return "yuksek"
    if oran <= 0.2:
        return "orta"
    return "dusuk"


def _duzelt(reddedilenler: list[dict]) -> dict[int, str]:
    """Finalize: reddedilen maddeleri, doğrulayıcının gerekçesiyle bir kez yeniden yazdırır. {id: yeni metin}, hata olursa {}."""
    sistem, talimat = _prompt_yukle(config.PROMPT_DUZELTME)
    girdi = _veri_temizle(json.dumps(reddedilenler, ensure_ascii=False, indent=1))
    try:
        cevap = _ask_json(talimat.replace("{maddeler}", girdi), sistem, schema.DUZELTME_CEVAP_SEMASI)
    except Exception:
        return {}
    duzeltmeler = cevap.get("duzeltmeler") if isinstance(cevap.get("duzeltmeler"), list) else []
    return {d["id"]: d["metin"].strip() for d in duzeltmeler
            if isinstance(d, dict) and isinstance(d.get("id"), int) and isinstance(d.get("metin"), str) and d["metin"].strip()}


def dogrula(sonuc: dict, kt_metni: str) -> tuple[dict, dict]:
    """Kod + LLM kontrolü, gerekirse bir düzeltme turu. Geçemeyen maddeleri kartlardan çıkarır, guven'i hesaplar.
    (sonuc, detay) döndürür."""
    desteklenmeyen = list(sonuc["dogrulama"]["desteklenmeyen"])
    detay = {"kod_elenen": 0, "sayi_elenen": 0, "llm_ilk_ret": 0, "duzeltilen": 0, "llm_elenen": 0,
             "kriter_ret": {k: 0 for k in schema.DOGRULAYICI_KRITERLER},
             "reddedilenler": []}  # rapor için: hangi madde, hangi gerekçeyle çıkarıldı

    def reddet(madde: dict, kontrol: str, neden: str) -> None:
        desteklenmeyen.append(madde["metin"])
        detay["reddedilenler"].append({**madde, "kontrol": kontrol, "neden": neden})

    # 1) Kod kontrolü
    adaylar = []  # (sıra, kart, madde); sıra kartlardaki ilk yerini korumak için
    for kart in schema.KARTLAR:
        for madde in sonuc["kartlar"][kart]:
            if not madde["kanit"] or kanit_skoru(madde["kanit"], kt_metni) < config.KANIT_ESIK:
                detay["kod_elenen"] += 1
                reddet(madde, "kod", "quote not found in leaflet")
            elif not sayilar_tutarli(madde["metin"], madde["kanit"], kt_metni):
                detay["sayi_elenen"] += 1
                reddet(madde, "sayi", "numbers differ")
            else:
                adaylar.append((len(adaylar), kart, madde))

    # 2) LLM kontrolü (sadece kod kontrolünü geçenler)
    kararlar = _llm_kontrol([{"id": i, "metin": m["metin"], "kanit": m["kanit"]} for i, _, m in adaylar])
    dogrulayici_tam = kararlar is not None and len(kararlar) == len(adaylar)
    detay["dogrulayici_calisti"] = kararlar is not None

    kalanlar, ilk_ret = [], []  # ilk_ret: (sıra, kart, madde, karar)
    for sira, kart, madde in adaylar:
        karar = (kararlar or {}).get(sira)
        # Doğrulayıcı çalışmadıysa veya bu maddeye cevap vermediyse madde kalır, güven düşürülür
        if karar is not None and not karar["destekleniyor"]:
            ilk_ret.append((sira, kart, madde, karar))
            for k in schema.DOGRULAYICI_KRITERLER:
                detay["kriter_ret"][k] += not karar[k]
        else:
            kalanlar.append((sira, kart, madde))
    detay["llm_ilk_ret"] = len(ilk_ret)

    # 3) Düzeltme (Finalize): reddedilenler gerekçeleriyle bir kez yeniden yazılır, sonra aynı kontrollerden tekrar geçer
    duzeltilmis = {}
    if config.DUZELTME_ACIK and ilk_ret:
        yeni = _duzelt([{"id": s, "metin": m["metin"], "kanit": m["kanit"], "neden": k["neden"]} for s, _, m, k in ilk_ret])
        tekrar = [(s, kart, {"metin": yeni[s], "kanit": m["kanit"]}) for s, kart, m, _ in ilk_ret
                  if s in yeni and sayilar_tutarli(yeni[s], m["kanit"], kt_metni)]
        kararlar2 = _llm_kontrol([{"id": s, "metin": m["metin"], "kanit": m["kanit"]} for s, _, m in tekrar]) or {}
        duzeltilmis = {s: (kart, m) for s, kart, m in tekrar if kararlar2.get(s, {}).get("destekleniyor")}
    for sira, kart, madde, karar in ilk_ret:
        if sira in duzeltilmis:
            kalanlar.append((sira, *duzeltilmis[sira]))
        else:
            detay["llm_elenen"] += 1
            reddet(madde, "llm", karar["neden"])
    detay["duzeltilen"] = len(duzeltilmis)

    kartlar = {kart: [] for kart in schema.KARTLAR}
    for _, kart, madde in sorted(kalanlar, key=lambda x: x[0]):
        kartlar[kart].append(madde)
    sonuc["kartlar"] = kartlar
    kalan = schema.madde_sayisi(sonuc)
    sonuc["dogrulama"] = {
        "desteklenmeyen": desteklenmeyen,
        "guven": _guven(kalan, detay["kod_elenen"] + detay["sayi_elenen"] + detay["llm_elenen"], dogrulayici_tam,
                        detay["dogrulayici_calisti"]),
    }
    return sonuc, detay


# ---------- Ana fonksiyon ----------

def analiz_detayli(kt_metni: str) -> tuple[dict, dict]:
    """analyze() ile aynı sonucu ve ölçüm için ara bilgileri döndürür. Hiçbir zaman hata fırlatmaz."""
    if config.USE_MOCK:
        return _mock(), {}

    dil = dil_tespit(kt_metni) if isinstance(kt_metni, str) else "en"
    try:
        if not isinstance(kt_metni, str) or len(kt_metni.strip()) < config.MIN_KT_KARAKTER:
            return schema.hata(_mesaj("kisa", dil)), {}
        kirpildi = len(kt_metni.strip()) > config.MAX_KT_KARAKTER
        if kirpildi:  # EMA'nın tam ürün belgesi gibi: önce kt_metni'nden sadece prospektüs bölümü ayrılmalı
            print(f"[analyze] Metin {len(kt_metni)} karakter, ilk {config.MAX_KT_KARAKTER} karakteri kullanılıyor.", file=sys.stderr)
        kt_metni = kt_metni.strip()[:config.MAX_KT_KARAKTER]

        sistem, talimat = _prompt_yukle(config.PROMPT_KARTLAR)
        talimat = talimat.replace("{dil_adi}", DIL_ADLARI[dil]).replace("{kt_metni}", _veri_temizle(kt_metni))
        ham = _ask_json(talimat, sistem, schema.KART_CEVAP_SEMASI)
        # Çıktı kontrolü: kartlar KT ile aynı dilde mi? Değilse bir kez uyararak tekrar sor
        if _cikti_dili(ham) not in (None, dil):
            uyari = (f"\n\nIMPORTANT: Your previous answer was not in {DIL_ADLARI[dil]}. "
                     f"Write every \"metin\" and question in {DIL_ADLARI[dil]}.")
            ham = _ask_json(talimat + uyari, sistem, schema.KART_CEVAP_SEMASI)

        analiz = ham.get("analiz") if isinstance(ham.get("analiz"), dict) else {}
        detay = {
            "dil": dil,
            "kirpildi": kirpildi,
            "cikti_dili": _cikti_dili(ham),
            "uyari_sayisi": len(analiz.get("uyarilar") or []),
            "belirsiz_sayisi": len(analiz.get("belirsiz_noktalar") or []),
            "soru_adayi_sayisi": len(analiz.get("soru_adaylari") or []),
        }
        if analiz.get("kt_mi") is False:
            return schema.hata(_mesaj("kt_degil", dil)), {**detay, "red_nedeni": analiz.get("red_nedeni", "")}

        sonuc = schema.normalize(ham)
        detay["taslak_madde"] = schema.madde_sayisi(sonuc)
        if detay["taslak_madde"] == 0:
            return schema.hata(_mesaj("bos", dil)), detay

        sonuc, dogrulama_detay = dogrula(sonuc, kt_metni)
        return sonuc, {**detay, **dogrulama_detay}
    except Exception as e:
        # Kullanıcıya sade mesaj; teknik ayrıntı terminale (Streamlit konsolu) ve ölçüm detayına
        print(f"[analyze] {type(e).__name__}: {e}", file=sys.stderr)
        return schema.hata(_mesaj("kota" if isinstance(e, KotaHatasi) else "hata", dil)), {"dil": dil, "hata_detay": str(e)}


def analyze(kt_metni: str) -> dict:
    return analiz_detayli(kt_metni)[0]
