"""
retriever.py -- guardrailed DPDP provision retrieval.

Given a finding's own DPDP anchor, return the verbatim provision text for THAT anchor only.
This is the clause-match guard: the retriever keys strictly on the section/rule the finding
already relies on, so it can never print a neighbouring or unrelated provision. If the exact
provision is not in the corpus, it returns an empty string rather than a best-guess clause.
Deterministic, no embeddings, no API keys.
"""
from __future__ import annotations
import json
import re
from pathlib import Path

_CORPUS = json.loads((Path(__file__).resolve().parent / "dpdp_corpus.json").read_text(encoding="utf-8"))
_ACT = _CORPUS["act"]
_RULE = _CORPUS["rule"]
SOURCE_LABEL = "DPDP Act, 2023 (Act 22 of 2023); DPDP Rules, 2025 (G.S.R. 846(E))"


def _act_text(section: str) -> str:
    if section in _ACT:
        return _ACT[section]
    # guarded fallback: only to the SAME base section number (e.g. S.8(3) -> S.8), never another
    base = re.match(r"(S\.\d+)", section or "")
    if base and base.group(1) in _ACT:
        return _ACT[base.group(1)]
    return ""


def provision_text(anchor: dict) -> str:
    """Verbatim provision(s) for this exact anchor, or '' if not in the corpus (never a guess)."""
    parts = []
    rule = (anchor or {}).get("rule")
    act = (anchor or {}).get("act_section")
    if rule and rule in _RULE:
        parts.append((rule, _RULE[rule]))
    if act:
        t = _act_text(act)
        if t:
            parts.append(("Act " + act, t))
    return "  ".join(f"{lbl} - {txt}" for lbl, txt in parts)


def clause_matches(anchor: dict, text: str) -> bool:
    """True iff `text` is the provision for THIS anchor (used as a build-time guard/assertion)."""
    return bool(text) and text == provision_text(anchor)
