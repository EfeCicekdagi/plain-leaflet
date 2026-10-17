"""analyze(): leaflet text -> 5 plain cards, questions for the pharmacist and the verification result.

The leaflet can be Turkish or English; the cards are written in the leaflet's language, and "evidence" is always in the leaflet's own language.

Flow (Draft -> Validate -> Finalize):
  1. Draft: prompt 1 (prompts/01_kartlar.txt) writes the cards and pharmacist questions.
  2. Code check: is every "evidence" really in the leaflet text? (difflib, threshold config.KANIT_ESIK)
     Do the numbers match? (numbers in the quote are in the leaflet, numbers in the plain sentence are in the quote)
  3. LLM check: prompt 2 (prompts/02_dogrulayici.txt) compares every plain sentence with its quote on 4 criteria.
  4. Fix: items the LLM rejected are rewritten once using its reason (03_duzeltme.txt) and go through steps 2 and 3 again.
  5. Final: items that still fail are removed from the cards and listed in "unsupported"; confidence is computed.
     The last check is human: every item is shown with its source, open points become questions for the pharmacist.
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


# Messages shown to the user, in the leaflet's language (English if unclear, as the UI is English)
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
    "error": {
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
    """"tr" or "en". Looks at letters only Turkish has (ğ ş ı İ, upper case included) and at common words.
    If it cannot decide: "en" (the UI is English). Letters are counted before lower-casing: the Turkish rule ("I" -> "ı")
    would make the English "If" look Turkish, and the normal rule would remove the "İ" from upper-case Turkish."""
    kelimeler = re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü]+", (metin or "")[:20000])
    tr = en = 0
    for k in kelimeler:
        kucuk = k.replace("İ", "i").lower()
        tr += (kucuk in _TR_KELIMELER) + 3 * any(h in k for h in "ğĞşŞıİ")
        en += kucuk in _EN_KELIMELER
    return "tr" if tr > en else "en"


DIL_ADLARI = {"tr": "Turkish", "en": "English"}


def _cikti_dili(ham: dict) -> str | None:
    """Language of the plain sentences the model wrote. None if there are no sentences."""
    kartlar = ham.get("cards") if isinstance(ham.get("cards"), dict) else {}
    metinler = [m.get("text", "") for k in kartlar.values() if isinstance(k, list) for m in k if isinstance(m, dict)]
    metin = " ".join(x for x in metinler if isinstance(x, str))
    return dil_tespit(metin) if metin.strip() else None


def _mesaj(anahtar: str, dil: str) -> str:
    return MESAJLAR[anahtar][dil]


def _prompt_yukle(yol) -> tuple[str, str]:
    """Splits a prompt file into (system, instruction). System: fixed rules for every call. Instruction: the task of this call."""
    with open(yol, encoding="utf-8") as f:
        metin = f.read()
    sistem, talimat = metin.split("### INSTRUCTION", 1)
    return sistem.replace("### SYSTEM", "", 1).strip(), talimat.strip()


def _veri_temizle(metin: str) -> str:
    """Removes the boundary tags from the document, so it cannot close its own tag and leak into the instructions."""
    return re.sub(r"</?\s*(leaflet|items)\s*>", " ", metin, flags=re.IGNORECASE)


def _json_coz(cevap: str) -> dict:
    try:
        veri = json.loads(cevap)
    except json.JSONDecodeError:
        # If the model wrapped the JSON in text, try what is between the first { and the last }
        bas, son = cevap.find("{"), cevap.rfind("}")
        if bas == -1 or son <= bas:
            raise
        veri = json.loads(cevap[bas:son + 1])
    if not isinstance(veri, dict):
        raise ValueError("model JSON nesnesi döndürmedi")
    return veri


def _ask_json(talimat: str, sistem: str, sema: dict, model: str | None = None) -> dict:
    """Validate -> repair -> validate again: if the answer is not valid JSON, asks once more with a warning."""
    try:
        return _json_coz(ask(talimat, sistem=sistem, sema=sema, model=model, dusunme=config.DUSUNME_BUTCESI))
    except (json.JSONDecodeError, ValueError):
        onar = talimat + "\n\nIMPORTANT: Your previous answer was not valid JSON. Return only valid JSON that matches the schema."
        return _json_coz(ask(onar, sistem=sistem, sema=sema, model=model, dusunme=config.DUSUNME_BUTCESI))


# ---------- Code check: is the quote in the leaflet text? ----------

def turkce_kucuk(metin: str) -> str:
    return metin.replace("İ", "i").replace("I", "ı").lower()


def _sadelestir(metin: str) -> str:
    """For comparison: Turkish lower case, one kind of quote and dash, join PDF line-end hyphens, collapse whitespace."""
    metin = unicodedata.normalize("NFKC", metin)  # PDF ligatures: "ﬂ" -> "fl"
    metin = turkce_kucuk(metin).replace("̇", "").replace("­", "")  # "i̇" (i + dot) and soft hyphen
    metin = re.sub(r"[‘’`´]", "'", metin)
    metin = re.sub(r"[“”«»]", '"', metin)
    metin = re.sub(r"[‐‑–—]", "-", metin)
    metin = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", metin)
    return re.sub(r"\s+", " ", metin).strip()


@lru_cache(maxsize=8)
def _kt_hazirla(kt_metni: str) -> str:
    """The leaflet ready for comparison, without whitespace. Cached so it is not recomputed for every item."""
    return _sadelestir(kt_metni).replace(" ", "")


_KISA_PARCA = 40       # fuzzy matching misleads on shorter parts, so only exact matches are accepted
# Parts joined with " ... " must appear in the leaflet in order and within this many characters (no whitespace): the same section.
# The widest spread in real outputs was 474 characters; parts collected from different sections are much further apart.
_BOLUM_ARALIGI = 1000
_AYIRICI = r"\s*(?:\.\.\.|…|:|•)\s*"


def kanit_skoru(kanit: str, kt_metni: str) -> float:
    """Similarity (0-1) of the quote to the most similar part of the leaflet text. 1.0 if it appears verbatim.

    If the quote is several parts joined with " ... " (or ":", "•") (heading ... list item):
    each part is searched separately and the lowest score is returned. The parts must also appear in the
    leaflet in order and close to each other; parts collected from different sections (e.g. a storage
    sentence ... a dose sentence) score 0.
    It also splits on ":": the model may join a heading and an item with ":"; this also catches a short,
    invented part added after a long real heading.
    Known limit: a word that appears in many places ("Nausea") may be missed if it is joined to the wrong heading.
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
    """Can one position be chosen for every part, in increasing order, with at most _BOLUM_ARALIGI from first to last?"""
    def ara(i: int, onceki: int, ilk: int) -> bool:
        if i == len(konumlar):
            return True
        return any(ara(i + 1, k, k if i == 0 else ilk) for k in konumlar[i]
                   if k >= onceki and (i == 0 or k - ilk <= _BOLUM_ARALIGI))
    return ara(0, -1, 0)


def _parca_bul(parca: str, m: str) -> tuple[float, list[int]]:
    """(similarity, positions in the leaflet). m: output of _kt_hazirla()."""
    k_bosluklu = _sadelestir(parca)
    k = k_bosluklu.replace(" ", "")  # no whitespace: split words from the PDF ("W ait", "K eep")
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

    # Fuzzy comparison. Candidate start points: the longest common block + places where a few pieces of the quote appear verbatim
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
    """Every number in the quote must be in the leaflet, and every number in the plain sentence in the quote. Catches changed doses, ages and durations in code."""
    return _sayilar(kanit) <= _kt_sayilari(kt_metni) and _sayilar(metin) <= _sayilar(kanit, kelimeler_dahil=True)


# ---------- LLM check: is the plain sentence faithful to its quote? ----------

def _llm_kontrol(maddeler: list[dict]) -> dict[int, dict] | None:
    """Returns {id: result}. Each result has the 4 criteria and "supported". None if the verifier call fails."""
    if not maddeler:
        return {}
    sistem, talimat = _prompt_yukle(config.PROMPT_DOGRULAYICI)
    girdi = _veri_temizle(json.dumps(maddeler, ensure_ascii=False, indent=1))
    try:
        sonuclar = _ask_json(talimat.replace("{maddeler}", girdi), sistem, schema.DOGRULAYICI_CEVAP_SEMASI,
                             model=config.DOGRULAYICI_MODEL).get("results", [])
    except Exception:
        return None
    kararlar = {}
    for s in sonuclar if isinstance(sonuclar, list) else []:
        if not isinstance(s, dict) or not isinstance(s.get("id"), int):
            continue
        kriterler = {k: s.get(k) for k in schema.DOGRULAYICI_KRITERLER}
        if not isinstance(s.get("supported"), bool) or not all(isinstance(v, bool) for v in kriterler.values()):
            continue
        # Even if the model says "supported", one failed criterion rejects the item (the decision is made in code)
        kararlar[s["id"]] = {**kriterler, "supported": s["supported"] and all(kriterler.values()),
                             "reason": s.get("reason", "")}
    return kararlar


def _guven(kalan: int, cikarilan: int, dogrulayici_tam: bool, dogrulayici_calisti: bool = True) -> str:
    # If no item went through the LLM verifier, confidence is low; the UI shows a "check with your pharmacist" warning
    if kalan == 0 or not dogrulayici_calisti:
        return "low"
    oran = cikarilan / (kalan + cikarilan)
    if oran == 0 and dogrulayici_tam:
        return "high"
    if oran <= 0.2:
        return "medium"
    return "low"


def _duzelt(reddedilenler: list[dict]) -> dict[int, str]:
    """Finalize: has rejected items rewritten once using the verifier's reason. {id: new text}, {} on error."""
    sistem, talimat = _prompt_yukle(config.PROMPT_DUZELTME)
    girdi = _veri_temizle(json.dumps(reddedilenler, ensure_ascii=False, indent=1))
    try:
        cevap = _ask_json(talimat.replace("{maddeler}", girdi), sistem, schema.DUZELTME_CEVAP_SEMASI)
    except Exception:
        return {}
    duzeltmeler = cevap.get("fixes") if isinstance(cevap.get("fixes"), list) else []
    return {d["id"]: d["text"].strip() for d in duzeltmeler
            if isinstance(d, dict) and isinstance(d.get("id"), int) and isinstance(d.get("text"), str) and d["text"].strip()}


def dogrula(sonuc: dict, kt_metni: str) -> tuple[dict, dict]:
    """Code + LLM check, with one fix round if needed. Removes items that fail from the cards and computes confidence.
    Returns (sonuc, detay)."""
    desteklenmeyen = list(sonuc["verification"]["unsupported"])
    detay = {"kod_elenen": 0, "sayi_elenen": 0, "llm_ilk_ret": 0, "duzeltilen": 0, "llm_elenen": 0,
             "kriter_ret": {k: 0 for k in schema.DOGRULAYICI_KRITERLER},
             "reddedilenler": []}  # for the report: which item was removed and why

    def reddet(madde: dict, kontrol: str, neden: str) -> None:
        desteklenmeyen.append(madde["text"])
        detay["reddedilenler"].append({**madde, "kontrol": kontrol, "reason": neden})

    # 1) Code check
    adaylar = []  # (order, card, item); order keeps the item's original place in the cards
    for kart in schema.KARTLAR:
        for madde in sonuc["cards"][kart]:
            if not madde["evidence"] or kanit_skoru(madde["evidence"], kt_metni) < config.KANIT_ESIK:
                detay["kod_elenen"] += 1
                reddet(madde, "kod", "quote not found in leaflet")
            elif not sayilar_tutarli(madde["text"], madde["evidence"], kt_metni):
                detay["sayi_elenen"] += 1
                reddet(madde, "sayi", "numbers differ")
            else:
                adaylar.append((len(adaylar), kart, madde))

    # 2) LLM check (only items that passed the code check)
    kararlar = _llm_kontrol([{"id": i, "text": m["text"], "evidence": m["evidence"]} for i, _, m in adaylar])
    dogrulayici_tam = kararlar is not None and len(kararlar) == len(adaylar)
    detay["dogrulayici_calisti"] = kararlar is not None

    kalanlar, ilk_ret = [], []  # ilk_ret: (order, card, item, decision)
    for sira, kart, madde in adaylar:
        karar = (kararlar or {}).get(sira)
        # If the verifier did not run or did not answer for this item, the item stays and confidence is lowered
        if karar is not None and not karar["supported"]:
            ilk_ret.append((sira, kart, madde, karar))
            for k in schema.DOGRULAYICI_KRITERLER:
                detay["kriter_ret"][k] += not karar[k]
        else:
            kalanlar.append((sira, kart, madde))
    detay["llm_ilk_ret"] = len(ilk_ret)

    # 3) Fix (Finalize): rejected items are rewritten once using their reason, then go through the same checks again
    duzeltilmis = {}
    if config.DUZELTME_ACIK and ilk_ret:
        yeni = _duzelt([{"id": s, "text": m["text"], "evidence": m["evidence"], "reason": k["reason"]} for s, _, m, k in ilk_ret])
        tekrar = [(s, kart, {"text": yeni[s], "evidence": m["evidence"]}) for s, kart, m, _ in ilk_ret
                  if s in yeni and sayilar_tutarli(yeni[s], m["evidence"], kt_metni)]
        kararlar2 = _llm_kontrol([{"id": s, "text": m["text"], "evidence": m["evidence"]} for s, _, m in tekrar]) or {}
        duzeltilmis = {s: (kart, m) for s, kart, m in tekrar if kararlar2.get(s, {}).get("supported")}
    for sira, kart, madde, karar in ilk_ret:
        if sira in duzeltilmis:
            kalanlar.append((sira, *duzeltilmis[sira]))
        else:
            detay["llm_elenen"] += 1
            reddet(madde, "llm", karar["reason"])
    detay["duzeltilen"] = len(duzeltilmis)

    kartlar = {kart: [] for kart in schema.KARTLAR}
    for _, kart, madde in sorted(kalanlar, key=lambda x: x[0]):
        kartlar[kart].append(madde)
    sonuc["cards"] = kartlar
    kalan = schema.madde_sayisi(sonuc)
    sonuc["verification"] = {
        "unsupported": desteklenmeyen,
        "confidence": _guven(kalan, detay["kod_elenen"] + detay["sayi_elenen"] + detay["llm_elenen"], dogrulayici_tam,
                        detay["dogrulayici_calisti"]),
    }
    return sonuc, detay


# ---------- Main function ----------

def analiz_detayli(kt_metni: str) -> tuple[dict, dict]:
    """Returns the same result as analyze() plus intermediate details for the evaluation. Never raises."""
    if config.USE_MOCK:
        return _mock(), {}

    dil = dil_tespit(kt_metni) if isinstance(kt_metni, str) else "en"
    try:
        if not isinstance(kt_metni, str) or len(kt_metni.strip()) < config.MIN_KT_KARAKTER:
            return schema.hata(_mesaj("kisa", dil)), {}
        kirpildi = len(kt_metni.strip()) > config.MAX_KT_KARAKTER
        if kirpildi:  # e.g. a full EMA product document: only the package leaflet part should be passed in
            print(f"[analyze] Metin {len(kt_metni)} karakter, ilk {config.MAX_KT_KARAKTER} karakteri kullanılıyor.", file=sys.stderr)
        kt_metni = kt_metni.strip()[:config.MAX_KT_KARAKTER]

        sistem, talimat = _prompt_yukle(config.PROMPT_KARTLAR)
        talimat = talimat.replace("{dil_adi}", DIL_ADLARI[dil]).replace("{kt_metni}", _veri_temizle(kt_metni))
        ham = _ask_json(talimat, sistem, schema.KART_CEVAP_SEMASI)
        # Output check: are the cards in the leaflet's language? If not, ask once more with a warning
        if _cikti_dili(ham) not in (None, dil):
            uyari = (f"\n\nIMPORTANT: Your previous answer was not in {DIL_ADLARI[dil]}. "
                     f"Write every \"text\" and question in {DIL_ADLARI[dil]}.")
            ham = _ask_json(talimat + uyari, sistem, schema.KART_CEVAP_SEMASI)

        analiz = ham.get("analysis") if isinstance(ham.get("analysis"), dict) else {}
        detay = {
            "dil": dil,
            "kirpildi": kirpildi,
            "cikti_dili": _cikti_dili(ham),
            "uyari_sayisi": len(analiz.get("warnings") or []),
            "belirsiz_sayisi": len(analiz.get("open_points") or []),
            "soru_adayi_sayisi": len(analiz.get("question_candidates") or []),
        }
        if analiz.get("is_leaflet") is False:
            return schema.hata(_mesaj("kt_degil", dil)), {**detay, "rejection_reason": analiz.get("rejection_reason", "")}

        sonuc = schema.normalize(ham)
        detay["taslak_madde"] = schema.madde_sayisi(sonuc)
        if detay["taslak_madde"] == 0:
            return schema.hata(_mesaj("bos", dil)), detay

        sonuc, dogrulama_detay = dogrula(sonuc, kt_metni)
        return sonuc, {**detay, **dogrulama_detay}
    except Exception as e:
        # A plain message for the user; technical details go to the terminal (Streamlit console) and the evaluation details
        print(f"[analyze] {type(e).__name__}: {e}", file=sys.stderr)
        return schema.hata(_mesaj("kota" if isinstance(e, KotaHatasi) else "error", dil)), {"dil": dil, "hata_detay": str(e)}


def analyze(kt_metni: str) -> dict:
    return analiz_detayli(kt_metni)[0]
