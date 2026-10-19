"""
docs.py -- read policy documents the crawler would otherwise miss: PDFs (and, where a scanned PDF
has no embedded text, an OCR fallback).

Why this matters for DPDP coverage: NGOs, colleges (.ac.in) and many government bodies publish
their privacy notice, grievance-redressal mechanism and data-protection policy as a PDF, not an
HTML page. The browser crawler drops .pdf links, so those duties were read as "Not disclosed" even
when the document plainly existed -- a false negative. Extracting the PDF's text and feeding it to
the same engine closes that gap.

Text extraction uses PyMuPDF (fitz), which returns the embedded text layer of a digital PDF
directly and fast. For a SCANNED PDF (image-only, no text layer) we fall back to OCR via Tesseract
-- but only when the tesseract binary is actually installed; otherwise OCR is skipped silently and
digital PDFs still work. Bounded by a max file size and page count so a huge PDF can't hang a scan.

Signal discipline: this module returns the document's TEXT to the engine for disclosure judging,
exactly as an HTML page's text is used. It never persists the file.
"""
from __future__ import annotations
import re
import shutil

_MAX_BYTES = 15 * 1024 * 1024        # skip very large PDFs (likely reports/datasets, not notices)
_MAX_PAGES = 40                      # read at most this many pages
_OCR_MIN_CHARS = 40                  # a page with less embedded text than this is treated as scanned


def pdf_available() -> bool:
    try:
        import fitz  # noqa: F401  (PyMuPDF)
        return True
    except Exception:
        return False


def ocr_available() -> bool:
    """OCR needs BOTH the pytesseract wrapper and the tesseract binary on PATH."""
    if shutil.which("tesseract") is None:
        return False
    try:
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401
        return True
    except Exception:
        return False


def _ocr_page(page) -> str:
    try:
        import io
        import pytesseract
        from PIL import Image
        pix = page.get_pixmap(dpi=200)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        return pytesseract.image_to_string(img) or ""
    except Exception:
        return ""


def extract_pdf_bytes(data: bytes) -> str:
    """Return the text of a PDF given its raw bytes. Uses the embedded text layer; falls back to
    OCR per page only for pages that have no text layer AND only when OCR is available."""
    if not data or not pdf_available():
        return ""
    import fitz
    text_parts: list[str] = []
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception:
        return ""
    use_ocr = ocr_available()
    try:
        for i, page in enumerate(doc):
            if i >= _MAX_PAGES:
                break
            try:
                t = page.get_text("text") or ""
            except Exception:
                t = ""
            if len(t.strip()) < _OCR_MIN_CHARS and use_ocr:
                t = _ocr_page(page) or t
            if t.strip():
                text_parts.append(t)
    finally:
        try:
            doc.close()
        except Exception:
            pass
    text = "\n".join(text_parts)
    return re.sub(r"[ \t]+", " ", text).strip()


def fetch_pdf_text(url: str, client=None, timeout: float = 25.0) -> str:
    """Fetch a PDF URL and return its extracted text. Verifies the response really is a PDF (by
    content-type or the %PDF magic) so an HTML error page is never parsed as a document."""
    if not pdf_available():
        return ""
    try:
        import httpx
    except Exception:
        return ""
    own = client is None
    try:
        if own:
            client = httpx.Client(timeout=timeout, follow_redirects=True)
        r = client.get(url)
        if r.status_code >= 400 or not r.content:
            return ""
        ctype = (r.headers.get("content-type") or "").lower()
        if "pdf" not in ctype and not r.content[:5].startswith(b"%PDF"):
            return ""
        if len(r.content) > _MAX_BYTES:
            return ""
        return extract_pdf_bytes(r.content)
    except Exception:
        return ""
    finally:
        if own and client is not None:
            try:
                client.close()
            except Exception:
                pass


_PDF_POLICY_RX = re.compile(
    r"privacy|policy|grievance|redress|nodal|data[-_ ]?protection|dpdp|gdpr|cookie|terms|legal|"
    r"notice|disclosure|personal[-_ ]?data", re.I)


def looks_like_policy_pdf(url: str, anchor_text: str = "") -> bool:
    """A PDF link worth extracting: it is a .pdf AND its URL or its anchor text is policy-relevant.
    This keeps us from downloading every annual report / brochure on the site."""
    u = (url or "").lower()
    if ".pdf" not in u:
        return False
    return bool(_PDF_POLICY_RX.search(u) or _PDF_POLICY_RX.search(anchor_text or ""))
