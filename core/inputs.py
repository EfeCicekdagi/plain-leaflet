"""Turn user uploads into plain text."""

import io
import unicodedata

from pypdf import PdfReader

IMAGE_PROMPT = (
    "This is a photo of a medicine package leaflet. Copy all of its text exactly as written, "
    "in reading order, keeping headings on their own lines. Do not summarise, translate, "
    "correct or add anything. If the photo contains no readable text, return nothing."
)

# File signatures of the image types the UI accepts
IMAGE_TYPES = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"RIFF": "image/webp",
}


def pdf_to_text(file: bytes) -> str:
    """Extract plain text from PDF bytes. Returns "" on error."""
    try:
        reader = PdfReader(io.BytesIO(file))
        pages = [page.extract_text() or "" for page in reader.pages]
        # NFKC splits ligatures such as "ﬂ" into plain letters
        return unicodedata.normalize("NFKC", "\n".join(pages)).strip()
    except Exception:
        return ""


def image_to_text(file: bytes) -> str:
    """Read the text of a leaflet photo with the model. Returns "" on error.

    Uses one model call (core/llm.py), so it counts against the quota.
    """
    try:
        mime_type = next((m for sig, m in IMAGE_TYPES.items() if file.startswith(sig)), None)
        if mime_type is None:
            return ""
        from core.llm import ask_image  # imported here so PDF reading works without the model library

        text = ask_image(IMAGE_PROMPT, file, mime_type)
        return unicodedata.normalize("NFKC", text).strip()
    except Exception:
        return ""
