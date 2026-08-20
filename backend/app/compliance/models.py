"""models.py -- Pydantic models for a DPDP compliance report.

Reconstructed from the engine's report output and the field schema read during the
working session. Uses Pydantic v2.
"""
from __future__ import annotations
from pydantic import BaseModel, Field


class FindingEvidence(BaseModel):
    policy_quote: str = ""          # verbatim site text that triggered the verdict
    policy_source_url: str = ""     # the page the quote came from
    observed: str = ""              # an observed fact (e.g. HTTPS true/false)
    attested: str = ""              # self-declared (DPO questionnaire) note
    dpdp_quote: str = ""            # verbatim DPDP provision the finding cites
    dpdp_source_label: str = ""     # label for the provision source


class PenaltyInfo(BaseModel):
    band: str = "other_provision"
    max: str = "up to 50 crore"


class Finding(BaseModel):
    id: str                         # slug, e.g. "c8-a-retention-period"
    title: str                      # the requirement (positive)
    finding: str = ""               # the problem (negative phrasing) for the report
    category: str
    dpdp_anchor: dict = Field(default_factory=dict)
    priority: str = "Low"           # requirement's inherent severity band
    severity: str = "Low"           # this finding's computed severity
    verdict: str = "Not disclosed"
    statement: str = ""             # detailed observation prose
    status: str = "New"
    confidence: float = 0.5
    affected_urls: list[str] = Field(default_factory=list)
    evaluated_pages: list[str] = Field(default_factory=list)
    evidence: FindingEvidence = Field(default_factory=FindingEvidence)
    penalty: PenaltyInfo = Field(default_factory=PenaltyInfo)
    impact: str = ""
    recommendation: str = ""
    references: list[str] = Field(default_factory=list)
    note: str = ""


class PerPageRow(BaseModel):
    sr: int
    page: str
    url: str
    page_type: str = "page"
    criticality: str = "Medium"
    processes: str = ""             # personal data / behaviour observed
    issue: str = ""                 # page-specific issue
    priority: str = "Info"


class Overall(BaseModel):
    grade: str = "E"
    adequacy: float = 0.0
    summary: str = ""
    at_a_glance: str = ""
    counts: dict = Field(default_factory=dict)   # severity -> count


class ComplianceReport(BaseModel):
    site: str
    url: str = ""
    scope: str = "site"
    pages_crawled: int = 0
    site_type: str = "auto"
    identity: dict = Field(default_factory=dict)
    watermark: str = ""
    generated_at: str = ""
    grounded: bool = True
    authenticated: bool = False
    inconclusive: bool = False
    coverage: dict = Field(default_factory=dict)
    overall: Overall = Field(default_factory=Overall)
    per_page: list[PerPageRow] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    tracker_inventory: list[dict] = Field(default_factory=list)
    cookie_inventory: list[dict] = Field(default_factory=list)
    exposure: list[dict] = Field(default_factory=list)
    disclaimer: str = ""
