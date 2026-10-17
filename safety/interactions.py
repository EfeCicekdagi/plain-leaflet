"""Rule-based drug interaction check (no LLM).

For every pair (A, B): does B's active substance, name or drug class appear
in the "Other medicines and A" section of A's leaflet? If so, a warning is
made with the sentence from A's leaflet as evidence.

Known limit: only the classes in DRUG_CLASSES are recognised; a leaflet
that names another class is missed.
"""

import re

from safety.sections import extract_leaflet, find_active_substances, find_other_medicines

MESSAGE = "Ask your pharmacist or doctor before taking these two medicines together."

# Other names leaflets use for the same substance
SYNONYMS = {
    "acetylsalicylic acid": ["aspirin"],
}

# Leaflets often name a class instead of a substance ("NSAIDs"). If B's
# substance is in a class, the class names are searched in A's leaflet too.
# Aspirin is left out of NSAIDs: leaflets list it separately and low-dose
# aspirin would warn on every NSAID line.
DRUG_CLASSES = {
    "nsaid": {
        "names": ["nsaid", "nsaids", "non-steroidal anti-inflammatory",
                  "anti-inflammatory medicines", "anti-inflammatory drugs"],
        "substances": ["ibuprofen", "naproxen", "diclofenac", "ketoprofen", "dexketoprofen",
                       "indometacin", "meloxicam", "piroxicam", "celecoxib", "etoricoxib"],
    },
    "anticoagulant": {
        "names": ["anticoagulant", "anticoagulants", "anti-coagulant", "anti-coagulants"],
        "substances": ["rivaroxaban", "apixaban", "edoxaban", "dabigatran", "warfarin",
                       "acenocoumarol", "phenprocoumon", "heparin", "enoxaparin"],
    },
    "antiplatelet": {
        "names": ["antiplatelet", "antiplatelets", "anti-platelet", "platelet aggregation inhibitors"],
        "substances": ["clopidogrel", "prasugrel", "ticagrelor", "ticlopidine"],
    },
    "proton pump inhibitor": {
        "names": ["proton pump inhibitor", "proton pump inhibitors", "ppi", "ppis"],
        "substances": ["esomeprazole", "omeprazole", "pantoprazole", "lansoprazole", "rabeprazole"],
    },
    "angiotensin ii receptor blocker": {
        "names": ["angiotensin ii receptor blocker", "angiotensin ii receptor blockers",
                  "angiotensin receptor blocker", "angiotensin receptor blockers"],
        "substances": ["valsartan", "losartan", "candesartan", "irbesartan", "telmisartan", "olmesartan"],
    },
    "statin": {
        "names": ["statin", "statins"],
        "substances": ["atorvastatin", "simvastatin", "rosuvastatin", "pravastatin",
                       "lovastatin", "fluvastatin", "pitavastatin"],
    },
}

# Bullet characters PDF extraction leaves at the start of list items,
# including Symbol-font private-use characters
BULLET = re.compile(r"^\s*(?:[•▪●◦*\-]|o(?=\s))\s*")
# Page numbers PDF extraction leaves on their own line or before a sentence
PAGE_NUMBER = re.compile(r"^\s*\d{1,3}\s*$")
INLINE_PAGE_NUMBER = re.compile(r"(?<=[.)])\s+\d{1,3}\s+(?=[A-Z])")

MIN_NAME_WORD = 5


def _search_terms(name: str, leaflet: str) -> list[str]:
    """Words that identify drug B, most specific first: substances, synonyms, name, classes."""
    substances = find_active_substances(leaflet)
    terms = []
    for substance in substances:
        terms.append(substance)
        terms.extend(SYNONYMS.get(substance, []))
    name = re.sub(r"\s+", " ", name).strip().lower()
    if name:
        terms.append(name)
        first_word = name.split(" ")[0]
        if len(first_word) >= MIN_NAME_WORD:
            terms.append(first_word)
    for drug_class in DRUG_CLASSES.values():
        if any(s in drug_class["substances"] for s in substances):
            terms.extend(drug_class["names"])
    return list(dict.fromkeys(terms))


def _sentences(section: str) -> list[str]:
    """Split a section into list items and sentences with clean spacing."""
    items, current = [], []
    for line in section.splitlines():
        if PAGE_NUMBER.match(line):
            continue
        if BULLET.match(line) and current:
            items.append(" ".join(current))
            current = []
        line = BULLET.sub("", line).strip()
        if line:
            current.append(line)
    if current:
        items.append(" ".join(current))

    sentences = []
    for item in items:
        item = INLINE_PAGE_NUMBER.sub(" ", re.sub(r"\s+", " ", item)).strip()
        sentences.extend(s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z])", item) if s)
    return sentences


def _find(term: str, sentences: list[str]) -> str:
    """Return the first sentence that contains term as a whole word, or ""."""
    pattern = re.compile(rf"(?<![a-z]){re.escape(term)}(?![a-z])")
    for sentence in sentences:
        if pattern.search(sentence.lower()):
            return sentence
    return ""


def check_interactions(leaflets: dict[str, str]) -> list[dict]:
    """Take {drug name: leaflet text} and return a list of warnings. Returns [] on error."""
    try:
        drugs = {}
        for name, text in leaflets.items():
            leaflet = extract_leaflet(text)
            drugs[name] = {
                "terms": _search_terms(name, leaflet),
                "sentences": _sentences(find_other_medicines(leaflet)),
            }

        warnings = []
        for drug_a, a in drugs.items():
            if not a["sentences"]:
                continue
            for drug_b, b in drugs.items():
                if drug_a == drug_b:
                    continue
                # Skip words that also identify A: A's leaflet always names its
                # own substance and class (e.g. clopidogrel in both Plavix and DuoPlavin)
                for term in (t for t in b["terms"] if t not in a["terms"]):
                    evidence = _find(term, a["sentences"])
                    if evidence:
                        warnings.append({
                            "drug_a": drug_a,
                            "drug_b": drug_b,
                            "matched": term,
                            "evidence": evidence,
                            "message": MESSAGE,
                        })
                        break
        return warnings
    except Exception:
        return []
