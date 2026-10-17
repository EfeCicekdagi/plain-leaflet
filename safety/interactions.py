"""Rule-based drug interaction check (no LLM).

For every pair (A, B): does B's active substance or name appear in the
"Other medicines and A" section of A's leaflet? If so, a warning is made
with the sentence from A's leaflet as evidence.

Known limit: leaflets that name a drug class ("non-steroidal
anti-inflammatory medicines (NSAIDs)") instead of a substance are missed.
"""

import re

from safety.sections import extract_leaflet, find_active_substances, find_other_medicines

MESSAGE = "Ask your pharmacist or doctor before taking these two medicines together."

# Other names leaflets use for the same substance
SYNONYMS = {
    "acetylsalicylic acid": ["aspirin"],
}

# Bullet characters PDF extraction leaves at the start of list items,
# including Symbol-font private-use characters
BULLET = re.compile(r"^\s*(?:[•▪●◦\-]|o(?=\s))\s*")

MIN_NAME_WORD = 5


def _search_terms(name: str, leaflet: str) -> list[str]:
    """Words that identify drug B: its substances, their synonyms and its name."""
    terms = []
    for substance in find_active_substances(leaflet):
        terms.append(substance)
        terms.extend(SYNONYMS.get(substance, []))
    name = re.sub(r"\s+", " ", name).strip().lower()
    if name:
        terms.append(name)
        first_word = name.split(" ")[0]
        if len(first_word) >= MIN_NAME_WORD:
            terms.append(first_word)
    return list(dict.fromkeys(terms))


def _sentences(section: str) -> list[str]:
    """Split a section into list items and sentences with clean spacing."""
    items, current = [], []
    for line in section.splitlines():
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
        item = re.sub(r"\s+", " ", item).strip()
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
                # own substance (e.g. clopidogrel in both Plavix and DuoPlavin)
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
