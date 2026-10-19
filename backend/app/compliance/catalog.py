"""catalog.py -- loads the 47-requirement DPDP framework from catalog.json."""
import json
from pathlib import Path

# Canonical verdict labels the engine emits (order matters for display).
VERDICTS = ("Compliant", "Partial", "Gap", "Not disclosed", "Not externally verifiable")

# Adequacy weight each verdict contributes to the grade (out of 1.0 per requirement).
WEIGHT = {"Compliant": 1.0, "Not externally verifiable": 0.75, "Partial": 0.5,
          "Gap": 0.0, "Not disclosed": 0.0, "Insufficient evidence": 0.0}

with (Path(__file__).resolve().parent / "catalog.json").open(encoding="utf-8") as _f:
    _DATA = json.load(_f)

CHECKS: list[dict] = _DATA["checks"]
CATEGORIES: list[str] = _DATA["categories"]
PENALTY_BANDS: dict = _DATA["penalty_bands"]


def penalty_for(check: dict) -> dict:
    band = check.get("penalty_band", "other_provision")
    return {"band": band, "max": PENALTY_BANDS.get(band, "up to 50 crore")}


def anchor_label(check: dict) -> str:
    a = check.get("dpdp_anchor", {})
    parts = []
    if a.get("rule"):
        parts.append(a["rule"])
    if a.get("act_section"):
        parts.append("Act " + a["act_section"])
    return "; ".join(parts)
