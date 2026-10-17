"""Data contract of the analyze() output. Only Person 1 changes it. The keys match Person 2's app.py (English).

Cards are in the language of the leaflet (Turkish or English). The JSON keys are always the same.

{
  "drug_name": "EXAMPLEDRUG 500 mg tablets",
  "cards": {
    "what_for":       [{"text": "plain sentence", "evidence": "verbatim quote from the leaflet"}],
    "how_to_use":     [...],
    "see_doctor_now": [...],
    "side_effects":   [...],
    "storage":        [...]
  },
  "pharmacist_questions": ["...", "..."],
  "verification": {
    "unsupported": ["item removed because its source could not be verified"],
    "confidence": "high | medium | low"
  }
}

On error it returns only {"error": "message to show the user"}.
"""

# The card order is the order in the UI
KARTLAR = ("what_for", "how_to_use", "see_doctor_now", "side_effects", "storage")

KART_BASLIKLARI = {
    "what_for": "Ne için kullanılır?",
    "how_to_use": "Nasıl kullanılır?",
    "see_doctor_now": "Hemen doktora başvurun",
    "side_effects": "Olası yan etkiler",
    "storage": "Nasıl saklanır?",
}

# Card titles for the English UI
KART_BASLIKLARI_EN = {
    "what_for": "What is it for?",
    "how_to_use": "How do I take it?",
    "see_doctor_now": "See a doctor right away if",
    "side_effects": "Possible side effects",
    "storage": "How do I store it?",
}

GUVEN_DEGERLERI = ("high", "medium", "low")

MAX_MADDE = 5  # most items per card
MAX_SORU = 5   # most pharmacist questions


def bos_sonuc(ilac_adi: str = "") -> dict:
    return {
        "drug_name": ilac_adi,
        "cards": {kart: [] for kart in KARTLAR},
        "pharmacist_questions": [],
        "verification": {"unsupported": [], "confidence": "low"},
    }


def hata(aciklama: str) -> dict:
    return {"error": aciklama}


def _yazi(deger) -> str:
    return deger.strip() if isinstance(deger, str) else ""


def normalize(ham: dict) -> dict:
    """Fits the model's JSON to the contract: fills missing fields, drops extra ones."""
    sonuc = bos_sonuc(_yazi(ham.get("drug_name")))

    kartlar = ham.get("cards") if isinstance(ham.get("cards"), dict) else {}
    for kart in KARTLAR:
        maddeler = kartlar.get(kart) if isinstance(kartlar.get(kart), list) else []
        for madde in maddeler:
            if not isinstance(madde, dict):
                continue
            metin, kanit = _yazi(madde.get("text")), _yazi(madde.get("evidence"))
            if metin and len(sonuc["cards"][kart]) < MAX_MADDE:
                sonuc["cards"][kart].append({"text": metin, "evidence": kanit})

    sorular = ham.get("pharmacist_questions") if isinstance(ham.get("pharmacist_questions"), list) else []
    sonuc["pharmacist_questions"] = [_yazi(s) for s in sorular if _yazi(s)][:MAX_SORU]

    dogrulama = ham.get("verification") if isinstance(ham.get("verification"), dict) else {}
    desteklenmeyen = dogrulama.get("unsupported") if isinstance(dogrulama.get("unsupported"), list) else []
    sonuc["verification"]["unsupported"] = [_yazi(d) for d in desteklenmeyen if _yazi(d)]
    if dogrulama.get("confidence") in GUVEN_DEGERLERI:
        sonuc["verification"]["confidence"] = dogrulama["confidence"]

    return sonuc


def madde_sayisi(sonuc: dict) -> int:
    return sum(len(sonuc.get("cards", {}).get(kart, [])) for kart in KARTLAR)


# ---------- Model answer schemas (Gemini response_schema, schema-first) ----------
# Field order (property_ordering) matters: the model writes "analysis" (step-by-step reasoning) first, then the cards.

def _nesne(alanlar: dict, sira: list[str]) -> dict:
    return {"type": "OBJECT", "properties": alanlar, "required": sira, "property_ordering": sira}


def _liste(oge: dict, en_fazla: int | None = None) -> dict:
    sema = {"type": "ARRAY", "items": oge}
    if en_fazla is not None:
        sema["max_items"] = en_fazla
    return sema


_YAZI = {"type": "STRING"}
_MADDE = _nesne({"text": _YAZI, "evidence": _YAZI}, ["text", "evidence"])

KART_CEVAP_SEMASI = _nesne(
    {
        "analysis": _nesne(
            {
                "is_leaflet": {"type": "BOOLEAN"},
                "rejection_reason": _YAZI,
                "warnings": _liste(_YAZI),
                "open_points": _liste(_YAZI),
                "question_candidates": _liste(_nesne(
                    {
                        "axis": {"type": "STRING", "enum": ["dose_timing", "other_medicines_food", "side_effect_watch", "special_groups", "missed_dose_storage"]},
                        "question": _YAZI,
                        "importance": {"type": "STRING", "enum": list(GUVEN_DEGERLERI)},
                    },
                    ["axis", "question", "importance"],
                )),
            },
            ["is_leaflet", "rejection_reason", "warnings", "open_points", "question_candidates"],
        ),
        "drug_name": _YAZI,
        "cards": _nesne({kart: _liste(_MADDE, MAX_MADDE) for kart in KARTLAR}, list(KARTLAR)),
        "pharmacist_questions": _liste(_YAZI, MAX_SORU),
    },
    ["analysis", "drug_name", "cards", "pharmacist_questions"],
)

DOGRULAYICI_KRITERLER = ("k1_no_added_info", "k2_same_meaning", "k3_condition_kept", "k4_same_numbers")

DOGRULAYICI_CEVAP_SEMASI = _nesne(
    {
        "results": _liste(_nesne(
            {"id": {"type": "INTEGER"}, "reason": _YAZI, **{k: {"type": "BOOLEAN"} for k in DOGRULAYICI_KRITERLER}, "supported": {"type": "BOOLEAN"}},
            ["id", "reason", *DOGRULAYICI_KRITERLER, "supported"],
        )),
    },
    ["results"],
)

DUZELTME_CEVAP_SEMASI = _nesne(
    {"fixes": _liste(_nesne({"id": {"type": "INTEGER"}, "text": _YAZI}, ["id", "text"]))},
    ["fixes"],
)
