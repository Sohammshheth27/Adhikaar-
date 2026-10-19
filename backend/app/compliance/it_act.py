"""
it_act.py -- the "enforceable today" layer: Information Technology Act, 2000 (s.43A, s.72A) and the
IT (Reasonable Security Practices and Procedures and Sensitive Personal Data or Information) Rules,
2011 ("SPDI Rules").

Why this exists: the DPDP Act, 2023 is enacted but its operative obligations are not yet in force
(they commence on notification, expected 2027). Until then, the law that ACTUALLY binds an Indian
body corporate handling Sensitive Personal Data or Information (SPDI) is the IT Act s.43A read with
the SPDI Rules, 2011. Adhikaar's 47 checks are DPDP-shaped; this module marks the subset that ALSO
has a basis enforceable *today*, so a reader sees which gaps carry present legal exposure versus
which become enforceable on DPDP commencement.

Scope honesty (important -- do not overclaim):
  * The SPDI Rules bite on a BODY CORPORATE (s.43A: a company / firm / sole proprietorship /
    association engaged in commercial or professional activities) that collects, holds or deals in
    SPDI. SPDI is a closed list: passwords; financial information such as bank account / card /
    payment-instrument details; physical, physiological and mental health condition; medical
    records; biometric information; sexual orientation (SPDI Rules r.3).
  * So "enforceable today" is reported as APPLICABLE only when we have evidence the site handles
    SPDI (e.g. a detected payment-card number, or a form collecting payment / password / health
    data). Otherwise it is reported as "not clearly applicable" -- the duty still stands under DPDP
    once in force.

Provision labels are plain-English references to real provisions by number; they are references,
not verbatim quotations, consistent with the report's existing disclaimer (information, not legal
advice). No provision text is fabricated.
"""
from __future__ import annotations

# Which of the 47 DPDP checks have a present IT-Act / SPDI-Rules basis, and that basis.
# duty_id -> {"provision": <label>, "basis": <plain-English obligation>}
_MAP: dict[int, dict] = {
    2:  {"provision": "SPDI Rules, 2011 r.5(3)",
         "basis": "A body corporate must make the provider of SPDI aware of the purpose of collection."},
    4:  {"provision": "SPDI Rules, 2011 r.5(1)",
         "basis": "Consent in writing must be obtained before collecting SPDI."},
    5:  {"provision": "SPDI Rules, 2011 r.5(2)",
         "basis": "SPDI may be collected only for a lawful purpose connected with a function of the body corporate and where necessary."},
    8:  {"provision": "SPDI Rules, 2011 r.5(4)",
         "basis": "SPDI must not be retained longer than required for the purpose."},
    9:  {"provision": "IT Act, 2000 s.43A; SPDI Rules, 2011 r.8",
         "basis": "Reasonable security practices (e.g. IS/ISO/IEC 27001 or equivalent) must be implemented; failure causing wrongful loss attracts compensation under s.43A."},
    12: {"provision": "SPDI Rules, 2011 r.5(1)",
         "basis": "Consent must be obtained by a clear act before collecting SPDI."},
    16: {"provision": "SPDI Rules, 2011 r.5(6)",
         "basis": "The provider of information must be permitted to review the SPDI they provided."},
    17: {"provision": "SPDI Rules, 2011 r.5(6)",
         "basis": "The provider must be able to have inaccurate or deficient SPDI corrected."},
    19: {"provision": "SPDI Rules, 2011 r.5(9)",
         "basis": "A Grievance Officer must be designated, with name and contact published, and grievances redressed within one month."},
    21: {"provision": "SPDI Rules, 2011 r.5(9)",
         "basis": "The Grievance Officer's name and contact details must be published for data-related complaints."},
    24: {"provision": "SPDI Rules, 2011 r.6; IT Act, 2000 s.72A",
         "basis": "Disclosure of SPDI to a third party requires prior consent; wrongful disclosure in breach of a lawful contract is punishable under s.72A."},
    33: {"provision": "SPDI Rules, 2011 r.4",
         "basis": "A body corporate handling SPDI must publish a clear and accessible privacy policy for its handling of such information."},
    38: {"provision": "IT Act, 2000 s.43A; SPDI Rules, 2011 r.8",
         "basis": "Secure transmission is part of reasonable security practices for SPDI."},
    39: {"provision": "IT Act, 2000 s.43A; SPDI Rules, 2011 r.8",
         "basis": "Protecting stored SPDI is part of the reasonable security practices s.43A requires."},
    40: {"provision": "IT Act, 2000 s.43A; SPDI Rules, 2011 r.8",
         "basis": "Access control over SPDI is part of reasonable security practices."},
}

# SPDI categories (IT Act terms) we can evidence from the data-category / collection detectors.
# Presidio entity / form-field -> SPDI? (payment card = financial information = SPDI).
_SPDI_PRESIDIO = {"CREDIT_CARD"}                 # financial information (r.3)
_SPDI_FIELDS = {"password", "card", "payment", "bank", "health", "medical", "biometric"}


def handles_spdi(data_categories: list[dict] | None, data_fields: set[str] | None) -> bool:
    """Evidence that the site handles Sensitive Personal Data or Information (SPDI)."""
    for row in (data_categories or []):
        if row.get("entity") in _SPDI_PRESIDIO:
            return True
    fields = {str(f).lower() for f in (data_fields or set())}
    return bool(fields & _SPDI_FIELDS)


def enforceable_today(duty_id: int) -> dict | None:
    """Return the IT-Act / SPDI basis for a duty, or None if it has no present-law basis."""
    return _MAP.get(duty_id)


def summary(unmet_duty_ids: list[int], spdi: bool) -> dict:
    """Report-facing enforceability summary.

    `unmet_duty_ids` are the duties recorded as a gap/partial/not-disclosed finding. We report how
    many of those also have an IT-Act / SPDI basis, and whether that basis is applicable now given
    the observed SPDI handling."""
    mapped = [d for d in unmet_duty_ids if d in _MAP]
    applicable = spdi
    if applicable:
        note = ("These gaps carry present legal exposure: the site appears to handle sensitive "
                "personal data (SPDI), so the IT Act, 2000 (s.43A) and the SPDI Rules, 2011 apply "
                "today, ahead of DPDP commencement.")
    else:
        note = ("No sensitive personal data (SPDI) handling was observed, so the IT Act / SPDI Rules "
                "basis is not clearly applicable; these duties become enforceable on DPDP "
                "commencement. (SPDI = passwords, financial/card, health, biometric or similar data.)")
    return {
        "spdi_observed": spdi,
        "applicable_now": applicable,
        "enforceable_today_count": len(mapped) if applicable else 0,
        "mapped_duty_ids": mapped if applicable else [],
        "provisions": sorted({_MAP[d]["provision"] for d in mapped}) if applicable else [],
        "note": note,
    }
