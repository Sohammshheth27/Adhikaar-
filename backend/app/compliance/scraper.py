"""
scraper.py -- Adhikaar site-wide content-extraction layer.

Sits between the CRAWLER (discovery: URLs, subdomains, pages) and the RAG / compliance engine.
Given the crawler's discovered pages, it retrieves and extracts CLEAN, analyzable text from the
WHOLE site -- every page and every document -- regardless of type, so the compliance engine can
inspect what is actually present, not merely that a page exists:

  * HTML (JS-rendered, passed in from the crawler; or fetched)  -> main content via trafilatura
  * PDF                                                          -> pdfplumber (pypdf fallback)
  * DOC / DOCX                                                   -> docx2txt (python-docx fallback)

It also discovers and fetches document links (PDF/DOCX) found across the pages, so policies posted
as files are captured. Output: a site corpus [{url, kind, text}] -> passed to the RAG for mapping
to DPDP requirements and to the in-force IT Act / SPDI Rules.
"""
import io, re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FTimeout
import httpx

_PDF_TIMEOUT = 30        # hard wall on a single PDF's parse; a malformed one is abandoned, not chased


def _bounded(fn, *args, seconds=_PDF_TIMEOUT):
    """Run fn with a hard timeout; on overrun return '' (the worker moves on, no stall)."""
    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(fn, *args).result(timeout=seconds)
    except (_FTimeout, Exception):
        return ""

_UA = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")}
_DOC_EXT = re.compile(r"\.(pdf|docx?|rtf)(\?|$)", re.I)


def _get(url, timeout=25):
    return httpx.get(url, headers=_UA, timeout=timeout, follow_redirects=True, verify=False)


_PDF_MAX_PAGES = 20      # policy text sits near the front; a cap stops malformed/huge PDFs stalling a worker
_TEXT_CAP = 120_000      # per-resource clean-text cap (chars)


def _pdf_text(data: bytes, max_pages: int = _PDF_MAX_PAGES) -> str:
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            t = "\n".join((pg.extract_text() or "") for pg in pdf.pages[:max_pages])
        if t.strip():
            return t[:_TEXT_CAP]
    except Exception:
        pass
    try:
        from pypdf import PdfReader
        pages = PdfReader(io.BytesIO(data)).pages
        return "\n".join((pages[i].extract_text() or "") for i in range(min(len(pages), max_pages)))[:_TEXT_CAP]
    except Exception:
        return ""


def _docx_text(data: bytes) -> str:
    try:
        import docx2txt
        t = docx2txt.process(io.BytesIO(data))
        if t and t.strip():
            return t
    except Exception:
        pass
    try:
        from docx import Document
        return "\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)
    except Exception:
        return ""


def _html_text(html: str, url: str = "") -> str:
    """Boilerplate-free main content via trafilatura; falls back to a tag-stripped body."""
    try:
        import trafilatura
        t = trafilatura.extract(html, url=url or None, include_comments=False,
                                include_tables=True, favor_recall=True)
        if t and len(t) > 150:
            return t
    except Exception:
        pass
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "form", "svg"]):
            tag.decompose()
        return re.sub(r"\n{3,}", "\n\n", soup.get_text("\n")).strip()
    except Exception:
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()


def extract_resource(url: str, rendered_html: str | None = None) -> dict:
    """Extract clean text from a single resource (page or document). Uses rendered_html when the
    crawler provides it (so JS content is included); otherwise fetches the resource itself."""
    low = url.lower().split("?")[0]
    try:
        if _DOC_EXT.search(low):
            ext = _DOC_EXT.search(low).group(1).lower()
            data = _get(url).content
            if len(data) > 12_000_000:          # skip oversized docs (scanned bundles) that stall extraction
                return {"url": url, "kind": "pdf" if ext == "pdf" else "docx", "text": "", "error": "oversized"}
            txt = _bounded(_pdf_text, data) if ext == "pdf" else _docx_text(data)
            return {"url": url, "kind": "pdf" if ext == "pdf" else "docx", "text": txt}
        if rendered_html is not None:
            return {"url": url, "kind": "html", "text": _html_text(rendered_html, url)}
        r = _get(url)
        ct = (r.headers.get("content-type", "") or "").lower()
        if "pdf" in ct:
            return {"url": url, "kind": "pdf", "text": _bounded(_pdf_text, r.content)}
        if "word" in ct or "officedocument.wordprocessing" in ct:
            return {"url": url, "kind": "docx", "text": _docx_text(r.content)}
        return {"url": url, "kind": "html", "text": _html_text(r.text, url)}
    except Exception as e:
        return {"url": url, "kind": "error", "text": "", "error": str(e)}


def find_document_links(html: str, base: str) -> list:
    from urllib.parse import urljoin
    out = [urljoin(base, m) for m in re.findall(r'href=["\']([^"\']+)', html or "") if _DOC_EXT.search(m)]
    return list(dict.fromkeys(out))


def scrape_site(pages: list, max_docs: int = 12) -> list:
    """pages: list of {url, html} from the crawler (rendered). Returns the full site corpus:
    every page's clean text + every linked PDF/DOCX document, extracted to clean text."""
    corpus, doc_urls = [], []
    for p in pages:
        url = p.get("url", "")
        corpus.append(extract_resource(url, rendered_html=p.get("html")))
        doc_urls += find_document_links(p.get("html", ""), url)
    seen = {c["url"] for c in corpus}
    for du in list(dict.fromkeys(doc_urls))[:max_docs]:
        if du not in seen:
            corpus.append(extract_resource(du))
            seen.add(du)
    return corpus
