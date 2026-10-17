"""Split package leaflet text into the sections we need (regex, no LLM).

Leaflets follow the EU template, so the same headings appear in every one:
- "B. PACKAGE LEAFLET" separates the patient leaflet in EMA PDFs
- "The active substance is ..." in section 6 ("What X contains")
- "Other medicines and X" in section 2, up to the next subheading
"""

import re

# EMA product information PDFs put the patient leaflet after a standalone
# "B. PACKAGE LEAFLET" heading line. The line anchors skip table-of-contents
# lines such as "ANNEX III LABELLING AND PACKAGE LEAFLET".
LEAFLET_HEADING = re.compile(r"^[ \t]*(?:B\.[ \t]*)?PACKAGE LEAFLET[ \t]*$", re.MULTILINE)

# "The active substance is X." / "The active substances are X and Y." /
# "The active substance in Brand is X." PDF extraction sometimes splits
# words ("substance s is"), hence the loose spacing.
ACTIVE_SENTENCE = re.compile(
    r"The active substance\s*s?\s+(?:in [^\n]{1,60}?\s+)?(?:is|are)\s+([^.\n]+)",
    re.IGNORECASE,
)

# Salt and form words dropped so "donepezil hydrochloride" becomes "donepezil"
SALT_WORDS = {
    "hydrochloride", "hemifumarate", "fumarate", "sodium", "potassium", "calcium",
    "magnesium", "hydrogen", "sulphate", "sulfate", "besilate", "maleate",
    "mesilate", "succinate", "tartrate", "monohydrate", "dihydrate", "trihydrate",
}

# Heading line only: references inside sentences such as
# (see "Other medicines and Entresto") contain quotes or brackets.
OTHER_MEDICINES_HEADING = re.compile(
    r"^[ \t]*Other medicines and [^\n\"“”()]{1,60}$", re.MULTILINE
)

# The subheading that follows "Other medicines and X" in the EU template.
# Subheadings are short lines; the length limit keeps wrapped body lines
# such as "... contrast medium that contains iodine into ..." from matching.
SECTION_END = re.compile(
    r"^[ \t]*(?=[^\n]{1,70}$)(?:"
    r"[^\n•▪\-]+\bwith (?:food|drink|alcohol)\b[^\n]*"
    r"|Pregnancy[^\n]*"
    r"|Driving and using machines[^\n]*"
    r"|[^\n•▪\-]+\bcontains? [^\n.,]+"
    r"|\d+\.\s*[A-Z][^\n]*"
    r")$",
    re.MULTILINE,
)

MAX_SECTION_CHARS = 8000

# "Package leaflet: Information for the user" is followed by the product line,
# e.g. "Xenleta 600 mg film-coated tablets"
LEAFLET_TITLE = re.compile(
    r"Package leaflet\s*:\s*Information for the (?:patient|user)\s*\n\s*([^\n]+)", re.IGNORECASE
)


def extract_leaflet(text: str) -> str:
    """Return only the patient leaflet part of an EMA PDF text.

    If there is no heading (e.g. eMC PDFs, which are leaflet only),
    the whole text is returned.
    """
    if not isinstance(text, str):
        return ""
    matches = list(LEAFLET_HEADING.finditer(text))
    if not matches:
        return text
    leaflet = text[matches[-1].end():].strip()
    return leaflet or text


def find_drug_name(text: str) -> str:
    """Return the medicine name from the leaflet title, without the strength.

    "Xenleta 600 mg film-coated tablets" -> "Xenleta". "" if not found.
    """
    if not isinstance(text, str):
        return ""
    match = LEAFLET_TITLE.search(text)
    if not match:
        return ""
    name = re.split(r"\s+\d", match.group(1).strip(), maxsplit=1)[0]
    return re.sub(r"\s+", " ", name).strip(" ,.")


def _clean_substance(raw: str) -> str:
    """'aliskiren (as hemifumarate)' -> 'aliskiren', 'donepezil hydrochloride' -> 'donepezil'."""
    name = re.sub(r"\([^)]*\)", " ", raw).lower()
    words = [w for w in re.findall(r"[a-z][a-z\-]*", name) if w not in SALT_WORDS]
    return " ".join(words)


def find_active_substances(text: str) -> list[str]:
    """Return the active substances named in the leaflet, lower case. [] if none found."""
    if not isinstance(text, str):
        return []
    substances = []
    for match in ACTIVE_SENTENCE.finditer(text):
        for part in re.split(r",|/|\band\b", match.group(1)):
            name = _clean_substance(part)
            if name and name not in substances:
                substances.append(name)
    return substances


def find_other_medicines(text: str) -> str:
    """Return the "Other medicines and X" section(s), or "" if not found.

    PDFs with several leaflets (one per strength) have several sections;
    they are joined with blank lines.
    """
    if not isinstance(text, str):
        return ""
    sections = []
    for heading in OTHER_MEDICINES_HEADING.finditer(text):
        start = heading.end()
        end = SECTION_END.search(text, start)
        stop = end.start() if end else start + MAX_SECTION_CHARS
        section = text[start:min(stop, start + MAX_SECTION_CHARS)].strip()
        if section and section not in sections:
            sections.append(section)
    return "\n\n".join(sections)
