"""Turn user uploads into plain text."""

import io

from pypdf import PdfReader


def pdf_to_text(file: bytes) -> str:
    """Extract plain text from PDF bytes. Returns "" on error."""
    try:
        reader = PdfReader(io.BytesIO(file))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages).strip()
    except Exception:
        return ""
