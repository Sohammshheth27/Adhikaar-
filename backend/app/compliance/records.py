"""
records.py -- detect personal records EXPOSED on a public page (data that should sit behind a login).

This is a defensive check: a public page that displays many people's contact details (a member,
donor or staff roster) or any government identifier is a serious DPDP exposure -- far more serious
than a missing policy clause. It maps to Act S.8(5) (security safeguards), S.6(1) (minimisation)
and, if minors are involved, S.9.

STRICTLY SIGNAL-ONLY: this module COUNTS pattern occurrences to decide whether bulk personal data is
publicly displayed. It never stores, logs, transmits or reproduces any individual's data -- only the
page URL and the counts appear in a finding, exactly like the file-exposure probe.
"""
from __future__ import annotations
import re

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?<!\d)(?:\+?91[-\s]?)?[6-9]\d{9}(?!\d)")          # Indian mobile number
_AADHAAR = re.compile(r"(?<!\d)\d{4}\s?\d{4}\s?\d{4}(?!\d)")             # 12-digit identifier format
_PAN = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")                            # PAN format
# Role/organisation mailboxes are NOT personal records -- exclude them so a normal contact page
# (info@, grievance@, support@ ...) never trips the check; only named individuals count.
_ROLE = re.compile(r"^(info|contact|support|admin|sales|careers?|media|hello|help|office|enquir\w*|"
                   r"hr|jobs|press|marketing|webmaster|no-?reply|team|mail|grievance|dpo|privacy|"
                   r"legal|compliance|donate|donations?|volunteer|general|feedback|complaints?|"
                   r"reception|accounts?|billing|noreply)@", re.I)


# Bare 12-digit / PAN patterns are noisy (phone-with-code, stats, transaction ids). Only count a
# government identifier when the page actually references that identifier -- a real leak of Aadhaar
# or PAN records labels the column.
_AADHAAR_KW = re.compile(r"aadhaar|uidai|\buid\b", re.I)
_PAN_KW = re.compile(r"\bpan\b|permanent account number", re.I)


def _counts(text: str) -> dict:
    t = text or ""
    personal_emails = {e for e in _EMAIL.findall(t) if not _ROLE.match(e)}
    aadhaar = len(_AADHAAR.findall(t)) if _AADHAAR_KW.search(t) else 0
    pan = len(set(_PAN.findall(t))) if _PAN_KW.search(t) else 0
    return {"emails": len(personal_emails), "phones": len(set(_PHONE.findall(t))),
            "aadhaar": aadhaar, "pan": pan}


def detect_published_records(pages: list[dict], email_thresh: int = 8, phone_thresh: int = 8) -> list[dict]:
    """Return exposure findings for pages that publicly display bulk personal records.

    A page trips the check if it shows many distinct contacts (>= threshold emails or phones -- a
    roster, not a single org contact) OR any government-identifier-format string. Counts only.
    """
    findings: list[dict] = []
    for p in pages:
        c = _counts(p.get("text", ""))
        bulk_contacts = c["emails"] >= email_thresh or c["phones"] >= phone_thresh
        gov_ids = c["aadhaar"] >= 2 or c["pan"] >= 2
        if not (bulk_contacts or gov_ids):
            continue
        what = []
        if c["emails"] >= email_thresh:
            what.append(f"{c['emails']} distinct email addresses")
        if c["phones"] >= phone_thresh:
            what.append(f"{c['phones']} distinct phone numbers")
        if c["aadhaar"]:
            what.append(f"{c['aadhaar']} Aadhaar-format number(s)")
        if c["pan"]:
            what.append(f"{c['pan']} PAN-format number(s)")
        findings.append({
            "id": "published_records", "severity": "Critical", "found": [p.get("url", "")],
            "detail": (f"This page publicly displays {', '.join(what)} without authentication. "
                       "Personal records of this kind should be held behind a login. "
                       "(Counts only; no individual's data is reproduced in this report.)"),
            "recommendation": ("Remove the personal records from the public page or place them behind "
                               "authentication, and display only the data the purpose needs."),
            "provision": "Act S.8(5); S.6(1); Rule 6",
        })
    return findings
