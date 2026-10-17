"""Split package leaflet text into the sections we need (regex, no LLM)."""

import re

# EMA product information PDFs put the patient leaflet after a standalone
# "B. PACKAGE LEAFLET" heading line. The line anchors skip table-of-contents
# lines such as "ANNEX III LABELLING AND PACKAGE LEAFLET".
LEAFLET_HEADING = re.compile(r"^[ \t]*(?:B\.[ \t]*)?PACKAGE LEAFLET[ \t]*$", re.MULTILINE)


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
