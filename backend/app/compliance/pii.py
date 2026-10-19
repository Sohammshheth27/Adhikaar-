"""
pii.py -- Presidio-backed PII / PCI identifier detection for Adhikaar.

Two jobs, both OUTSIDE the verdict/judge path (the judge scores disclosure adequacy; this scores
what personal / financial / government-identifier data a site actually HANDLES or LEAKS):

  1. EXPOSURE  -- counts of high-sensitivity identifiers displayed on a public page (Aadhaar, PAN,
                  credit card, GSTIN, voter id, passport). Feeds records.detect_published_records:
                  a public page showing these is a Critical S.8(5)/S.6(1) exposure.
  2. CATEGORIES -- which categories of personal / sensitive / financial data the site processes,
                  summarised for the report so the reader sees the data-sensitivity at a glance.

Detection uses Microsoft Presidio's PATTERN recognizers run DIRECTLY (no spaCy NLP engine is
loaded), so it is deterministic, fast and auditable, and adds validation the old regex lacked:
Aadhaar is Verhoeff-checksum validated, credit cards are Luhn validated. A keyword/context gate
(the identifier's name must appear near the match) keeps precision high for the context-sensitive
types (PAN, GSTIN, voter, passport).

STRICTLY SIGNAL-ONLY, exactly like records.py and exposure.py: this module COUNTS matches to decide
whether sensitive data is present or leaked. It never stores, logs, transmits or reproduces any
individual's identifier -- only categories and counts leave this module.

Falls back cleanly (available() -> False) when presidio-analyzer is not installed; records.py then
uses its own regex detectors, so the tool always runs.
"""
from __future__ import annotations
import re

# entity -> (keyword regex that must appear near the match, or None if the validator alone suffices)
_CONTEXT = {
    "IN_AADHAAR":  re.compile(r"aadhaar|uidai|\buid\b", re.I),        # Verhoeff-validated; still gate
    "IN_PAN":      re.compile(r"\bpan\b|permanent account number", re.I),
    "IN_GSTIN":    re.compile(r"\bgstin\b|\bgst\b|goods and services tax", re.I),
    "IN_VOTER":    re.compile(r"voter|epic|electoral", re.I),
    "IN_PASSPORT": re.compile(r"passport", re.I),
    "CREDIT_CARD": None,                                              # Luhn is specific enough
}
# entity -> human label + the DPDP data category it evidences
_CATEGORY = {
    "IN_AADHAAR":  ("Aadhaar", "Government identifier (high-sensitivity)"),
    "IN_PAN":      ("PAN", "Government identifier / financial"),
    "IN_GSTIN":    ("GSTIN", "Business/tax identifier"),
    "IN_VOTER":    ("Voter ID", "Government identifier (high-sensitivity)"),
    "IN_PASSPORT": ("Passport", "Government identifier (high-sensitivity)"),
    "CREDIT_CARD": ("Credit/debit card", "Financial data (PCI)"),
}
_MIN_SCORE = 0.30            # format+validator floor; context gate does the rest

_RECOGNIZERS = None
_WINDOW = 48                 # chars either side of a match to search for the context keyword


def available() -> bool:
    try:
        import presidio_analyzer  # noqa: F401
        return True
    except Exception:
        return False


def _recognizers():
    global _RECOGNIZERS
    if _RECOGNIZERS is None:
        from presidio_analyzer.predefined_recognizers import (
            InAadhaarRecognizer, InPanRecognizer, InVoterRecognizer,
            InPassportRecognizer, CreditCardRecognizer)
        recs = {
            "IN_AADHAAR": InAadhaarRecognizer(),
            "IN_PAN": InPanRecognizer(),
            "IN_VOTER": InVoterRecognizer(),
            "IN_PASSPORT": InPassportRecognizer(),
            "CREDIT_CARD": CreditCardRecognizer(),
        }
        try:                                         # GSTIN only in some presidio versions
            from presidio_analyzer.predefined_recognizers import InGstinRecognizer
            recs["IN_GSTIN"] = InGstinRecognizer()
        except Exception:
            pass
        _RECOGNIZERS = recs
    return _RECOGNIZERS


def _context_ok(entity: str, text: str, start: int, end: int) -> bool:
    kw = _CONTEXT.get(entity)
    if kw is None:
        return True
    window = text[max(0, start - _WINDOW): min(len(text), end + _WINDOW)]
    return bool(kw.search(window))


def scan(text: str) -> dict[str, int]:
    """Return {entity: count} of validated, context-confirmed identifier matches in `text`.
    Counts of DISTINCT matched spans (by surface form) per entity; values are never retained."""
    if not text or not available():
        return {}
    out: dict[str, set] = {}
    try:
        for entity, rec in _recognizers().items():
            try:
                results = rec.analyze(text, entities=[entity], nlp_artifacts=None)
            except Exception:
                continue
            # For context-gated types the keyword IS the precision mechanism, so a format match
            # (low base score) plus the nearby keyword is sufficient; types without a context
            # keyword (credit card) must clear the full validator score (Luhn gives a high one).
            has_ctx = _CONTEXT.get(entity) is not None
            floor = 0.05 if has_ctx else _MIN_SCORE
            for r in results:
                if r.score < floor:
                    continue
                if not _context_ok(entity, text, r.start, r.end):
                    continue
                out.setdefault(entity, set()).add(text[r.start:r.end])
    except Exception:
        return {}
    return {e: len(v) for e, v in out.items() if v}


def categories(text: str) -> list[dict]:
    """Report-facing summary of the sensitive-data categories present in `text`.
    Returns [{entity, label, category, count}], highest count first. Counts only."""
    counts = scan(text)
    rows = []
    for entity, n in counts.items():
        label, cat = _CATEGORY.get(entity, (entity, "Personal data"))
        rows.append({"entity": entity, "label": label, "category": cat, "count": n})
    rows.sort(key=lambda r: -r["count"])
    return rows
