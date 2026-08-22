"""
semantic.py -- semantic disclosure judging (no keyword lists).

For each DPDP duty we hold an exemplar of *what a compliant disclosure actually says*. We split the
policy into sentences, embed them with an open-source sentence-transformer, and score each duty by
the closest sentence's meaning. This catches paraphrases a keyword list would miss -- e.g. "you may
raise your concern with our nodal officer" satisfies the grievance duty with no keyword in common.

Deterministic (fixed local model, no API keys). Model downloads once (~90 MB) on first use.
Verdict thresholds are on cosine similarity of normalized embeddings and are tunable.
"""
from __future__ import annotations
import re

_MODEL = None
_EX_EMB = None
T_HIGH = 0.55        # >= -> Compliant. GOLD-calibrated: fine-tuned model scores F1 0.73 @ 0.55 (up from
T_PARTIAL = 0.47     # 0.58 pre-tune). Trained on 8 strong real policies (1,281 pairs) via the hardened crawler.

# What a COMPLIANT disclosure states, per requirement id. Phrased as a policy would phrase it.
EXEMPLARS: dict[int, list[str]] = {
    1: ["We collect the following categories of personal data: name, email, phone, address, payment details."],
    2: ["We collect your personal data for the specific purpose of processing your request and providing the service."],
    3: ["This privacy notice explains in clear and plain language how we handle your personal data."],
    4: ["We process your personal data on the lawful basis of your consent or a legitimate use permitted by law."],
    5: ["We collect only the personal data that is necessary for the stated purpose and nothing more."],
    6: ["Where we rely on a legitimate use, it falls within the categories permitted under Section 7 of the Act."],
    7: ["We take reasonable steps to keep your personal data accurate, complete and up to date."],
    8: ["We retain your personal data only for as long as necessary and erase it when the purpose is served; our retention period is stated."],
    9: ["We protect your personal data with reasonable security safeguards such as encryption and access controls."],
    10: ["In the event of a personal data breach we will notify the affected users and the Data Protection Board."],
    11: ["You may withdraw your consent at any time, as easily as you gave it, using the route provided."],
    12: ["We obtain your consent through a clear affirmative action; it is not pre-ticked or assumed."],
    13: ["You may manage your consent through a registered Consent Manager."],
    14: ["You can review the consent you have given and we maintain records of consent."],
    15: ["For users under eighteen we obtain verifiable parental consent and we do not track or target advertising at children."],
    16: ["You have the right to access a summary of the personal data we hold about you and how it is processed."],
    17: ["You have the right to correction of your personal data."],
    18: ["You have the right to erasure or deletion of your personal data."],
    19: ["You may raise a grievance or complaint with our grievance officer or nodal officer through the redressal mechanism provided."],
    20: ["You have the right to nominate another individual to exercise your rights on your behalf."],
    21: ["For any questions about your personal data, contact our Data Protection Officer or grievance officer at the address provided."],
    22: ["We have appointed and published a Data Protection Officer as a Significant Data Fiduciary."],
    23: ["We engage data processors only under a valid written contract or data processing agreement."],
    24: ["We may share your personal data with the following categories of third parties and recipients."],
    25: ["We oversee any sub-processors engaged by our processors."],
    26: ["Our security obligations flow down to our processors by contract."],
    27: ["We may transfer your personal data to countries outside India for processing."],
    28: ["We comply with restrictions on transfers to notified restricted countries."],
    29: ["Your personal data is stored and hosted at the locations described here."],
    30: ["We undertake a Data Protection Impact Assessment for high-risk processing as a Significant Data Fiduciary."],
    31: ["We apply privacy by design and undergo periodic independent audits."],
    32: ["We minimise the personal data we collect by design and default."],
    33: ["Our privacy policy is published and reachable from the website."],
    34: ["We publish a cookie policy describing the cookies and tracking technologies we use."],
    35: ["Our terms of service are published."],
    36: ["Our notice is available in an accessible form and in Indian languages where relevant."],
    37: ["Our registered office address and entity contact details are published."],
    38: ["The website is served securely over HTTPS."],
    39: ["Personal data is encrypted at rest."],
    40: ["We maintain access controls and logging over personal data."],
    41: ["We have an internal data protection policy and governance in place."],
    42: ["Our staff who handle personal data are trained on data protection."],
    43: ["We maintain records of our processing activities."],
    44: ["We maintain an incident response plan for personal data breaches."],
    45: ["We manage vendor and third-party risk."],
    46: ["We meet the additional obligations of a Significant Data Fiduciary including Board reporting."],
    47: ["We perform a periodic compliance review or audit."],
}


def available() -> bool:
    try:
        import sentence_transformers  # noqa: F401
        return True
    except Exception:
        return False


def _model():
    global _MODEL, _EX_EMB
    if _MODEL is None:
        import os as _os
        from sentence_transformers import SentenceTransformer
        _local = _os.path.join(_os.path.dirname(__file__), "models", "adhikaar-minilm")
        _MODEL = SentenceTransformer(_local if _os.path.isdir(_local) else "all-MiniLM-L6-v2")
        ids = list(EXEMPLARS)
        flat = [s for i in ids for s in EXEMPLARS[i]]
        emb = _MODEL.encode(flat, convert_to_tensor=True, normalize_embeddings=True)
        _EX_EMB = {}
        k = 0
        for i in ids:
            n = len(EXEMPLARS[i])
            _EX_EMB[i] = emb[k:k + n]
            k += n
    return _MODEL


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+|•|\|", text or "")
    out, seen = [], set()
    for p in parts:
        p = re.sub(r"\s+", " ", p).strip()
        if 15 <= len(p) <= 400 and p.lower() not in seen:
            seen.add(p.lower()); out.append(p)
    return out[:500]


def judge_all(policy_text: str, t_high: float = T_HIGH, t_partial: float = T_PARTIAL) -> dict[int, tuple[str, float]]:
    """Return {check_id: (verdict, score)} judged semantically against the policy text."""
    sents = _sentences(policy_text)
    if not sents:
        return {i: ("Not disclosed", 0.0, "") for i in EXEMPLARS}  # 3-tuple, consistent with below
    from sentence_transformers import util
    model = _model()
    sent_emb = model.encode(sents, convert_to_tensor=True, normalize_embeddings=True)
    out = {}
    for cid, ex_emb in _EX_EMB.items():
        col_max = util.cos_sim(ex_emb, sent_emb).max(dim=0).values   # best exemplar sim per sentence
        j = int(col_max.argmax())
        m = float(col_max[j])
        verdict = "Compliant" if m >= t_high else "Partial" if m >= t_partial else "Not disclosed"
        out[cid] = (verdict, round(m, 3), sents[j] if verdict != "Not disclosed" else "")
    return out
