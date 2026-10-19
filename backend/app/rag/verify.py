"""
verify.py -- Stage-2 evidence verification for the DPDP disclosure judge.

Stage-1 (semantic.py) retrieves, per duty, the policy sentence whose MEANING is closest to a
compliant disclosure. That is high-recall but over-credits: a phone directory ("Grievance Cell -
Office 1194 1240") is topically close to the grievance duty yet asserts nothing. Stage-2 verifies
each retrieved candidate the way a human auditor would -- and, crucially, by the KIND of evidence
the duty actually needs:

  * structural   -> the duty is about something EXISTING (a privacy policy, HTTPS, a cookie
                    policy, a published contact). Verified deterministically from crawl signals,
                    never from sentence similarity.
  * content      -> the duty is a DISCLOSURE LIST (what data is collected, who it is shared with).
                    Verified by an assertion gate: the span must be a substantive sentence about
                    personal data, not a heading, a table row, or boilerplate.
  * propositional -> the duty is a CLAIM the policy must make (we retain only as long as needed;
                    you may withdraw consent). Verified by natural-language INFERENCE: does the
                    span entail the duty's minimal legal test? An empty/near-zero entailment is
                    rejected. This is what kills the topically-similar-but-non-committal matches.

No LLM. One local NLI cross-encoder + the deterministic engine signals + a light assertion gate.
"""
from __future__ import annotations
import re

# ---- duty routing -----------------------------------------------------------------------------
STRUCTURAL = {33, 34, 35, 37, 38}          # existence facts -> decided by crawl signals, not text
CONTENT    = {1, 24, 29}                    # disclosure lists -> assertion gate + topical match
INTERNAL: set[int] = set()
# ^ (was a blanket abstain on governance/training/records/vendor/DPIA duties.) Removed: Adhikaar
#   scores DISCLOSURE adequacy, so a policy that DISCLOSES an internal control ("we maintain
#   incident-response measures", "our nodal grievance officer is ...") should be credited for the
#   commitment. Blanket-refusing them created false negatives (e.g. Tata Neu #44 entailed 1.00 yet
#   scored 0). False positives from generic security text are handled by the TIGHT per-duty
#   hypotheses + entailment, not by suppressing the duty. Kept as an (empty) hook for duties we may
#   later prove are never externally disclosable.

SIM_FLOOR = 0.35                            # light topical-relevance floor; entailment is the real
                                            # discriminator, so this only rejects clearly off-topic spans

# minimal legal test per duty, phrased so a genuine disclosure ENTAILS it (propositional lane)
HYP: dict[int, str] = {
    2:  "Personal data is collected for a specified purpose.",
    3:  "The notice explains how the organization handles personal data.",
    4:  "Processing of personal data relies on consent or a lawful basis.",
    5:  "Only the personal data necessary for the purpose is collected.",
    6:  "Processing relies on a legitimate use permitted by law.",
    7:  "Personal data is kept accurate and up to date.",   # single duty (accuracy); kept as one claim
    8:  "Personal data is retained only as long as necessary.",
    9:  "Personal data is protected with reasonable security safeguards.",
    10: "The organization informs affected individuals when their personal data is breached.",
    11: "Consent can be withdrawn at any time.",
    12: "Consent is obtained through a clear affirmative action.",
    13: "Consent is managed through a registered consent manager.",
    14: "Records of the consent given by the user are maintained.",
    15: "Children may use the service only with the involvement of a parent or guardian.",
    16: "An individual can access the personal data held about them.",
    17: "An individual can correct their personal data.",
    18: "An individual can have their personal data erased.",
    19: "An individual can raise a grievance about their personal data through a redressal mechanism.",
    20: "An individual can nominate someone to exercise their data rights.",
    21: "A contact is provided for questions or complaints about personal data.",
    22: "A Data Protection Officer has been appointed and published.",
    23: "Data processors are engaged only under a written contract.",
    25: "Sub-processors engaged by processors are overseen.",
    26: "Security obligations are passed down to processors by contract.",
    27: "Personal data may be transferred to other countries.",
    28: "Transfers to restricted countries are limited.",
    30: "A data protection impact assessment is carried out for high-risk processing.",
    31: "Independent audits of data protection are carried out.",
    32: "The personal data collected is minimised by design.",
    36: "The notice is available in an accessible form or in Indian languages.",
    39: "Personal data is encrypted at rest.",
    40: "Access to personal data is restricted to authorized staff.",
    41: "The organization maintains an internal policy for staff on handling personal data.",
    42: "Staff who handle personal data are trained on data protection.",
    43: "Records of processing activities are maintained.",
    44: "An incident response plan for data breaches is maintained.",
    45: "Third-party and vendor data risk is managed.",
    46: "The additional obligations of a significant data fiduciary are met.",
    47: "A periodic compliance review or audit is performed.",
}

# decision bands (calibratable). Compliant needs an assertive sentence AND (a STRONG topical match
# OR high entailment). S_STRONG is deliberately high (0.70): the sim-only path exists only to rescue
# genuine clauses NLI is brittle on (a retention clause can be sim 0.76 yet entail ~0); it must not
# admit merely-similar off-topic text (an admissions contact matched a privacy-contact duty at 0.63).
# DPO-calibrated bands (set from compliance-officer principles, not fitted to the test labels):
#   Compliant requires a genuine COMMITMENT (entailment of the legal test), never topical similarity
#   alone, so the old sim-only->Compliant path (S_STRONG) is removed. Partial is "addressed but not
#   committed": it fires on topical PRESENCE (S_PART) OR weak entailment (E_PART), capturing the
#   "weak but present" case the old AND-logic dropped into Gap.
E_HIGH, E_PART = 0.60, 0.22                  # Compliant entailment bar; weak-entailment entry to Partial
S_PART = 0.50                                # topical-presence entry to Partial (addressed but vague)
S_STRONG = 0.70                              # retained for reference; no longer a Compliant shortcut

_BOILERPLATE = re.compile(
    r"^\s*(all rights reserved|privacy statement|terms(?: of service| and conditions)?|"
    r"copyright|home|contact us|read more|click here|sitemap|menu|search|login|©.*)\.?\s*$", re.I)


def structural_signals(policy_text: str, policy_source_urls=None, corpus_text: str = "") -> dict:
    """Deterministic detectors for the STRUCTURAL existence duties (#33 privacy policy, #34 cookie
    policy, #35 terms, #37 contact). Must isolate a GENUINE artifact, not any legal document: a
    privacy policy is not credited merely because the site has 800 characters of text or links some
    unrelated PDF (a syllabus, a code of conduct). Privacy requires a privacy-specific URL or
    privacy-policy language; contact requires a real email or a registered-office address."""
    t = ((corpus_text or "") + "\n" + (policy_text or "")).lower()
    urls = [str(u).lower() for u in (policy_source_urls or []) if u]
    uh = lambda *ks: any(any(k in u for k in ks) for u in urls)
    policy = (uh("privacy", "data-protection", "data_protection")
              or bool(re.search(r"\bprivacy (policy|statement|notice)\b", t))
              or ("personal information" in t and "collect" in t)
              or ("personal data" in t and bool(re.search(r"\bwe (collect|process|use)\b", t))))
    cookie = (uh("cookie") or "cookie policy" in t
              or ("cookies" in t and ("consent" in t or "manage" in t or "we use cookies" in t)))
    terms = uh("/terms", "terms-", "tos") or bool(re.search(r"terms (of (use|service|sale)|and conditions)", t))
    contact = (bool(re.search(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", t))
               or "registered office" in t or "corporate office" in t)
    return {"policy_found": policy, "cookie_policy": cookie, "terms_found": terms, "contact_found": contact}


def _assertive(s: str) -> bool:
    """A substantive claim sentence, not a heading, phone-table row, or boilerplate."""
    s = (s or "").strip()
    words = s.split()
    if len(s) < 25 or len(words) < 5:
        return False
    digits = sum(c.isdigit() for c in s)
    if digits / max(len(s), 1) > 0.25:            # phone/extension tables are digit-heavy
        return False
    if _BOILERPLATE.match(s):
        return False
    return True


# ---- NLI cross-encoder (lazy, local, cached once) ---------------------------------------------
_CE = None
_ENT = None

def _nli():
    global _CE, _ENT
    if _CE is None:
        import math  # noqa: F401
        from sentence_transformers import CrossEncoder
        _CE = CrossEncoder("cross-encoder/nli-deberta-v3-base")
        id2 = _CE.model.config.id2label
        _ENT = next(i for i, l in id2.items() if "entail" in l.lower())
    return _CE


def p_entail(premise: str, hypothesis: str) -> float:
    import math
    logits = _nli().predict([(premise, hypothesis)])[0]
    e = [math.exp(x) for x in logits]
    return e[_ENT] / sum(e)


def p_entail_batch(pairs: list[tuple[str, str]]) -> list[float]:
    """Entailment probability for many (premise, hypothesis) pairs in ONE forward pass.
    On CPU this turns ~100 sequential NLI calls into a single batched matmul -- the difference
    between a ~minute and a few seconds per scan. Returns a list aligned to `pairs`."""
    import math
    if not pairs:
        return []
    logits = _nli().predict(pairs)        # (n, 3)
    out = []
    for row in logits:
        e = [math.exp(x) for x in row]
        out.append(e[_ENT] / sum(e))
    return out


def nli_available() -> bool:
    try:
        _nli(); return True
    except Exception:
        return False


# ---- per-duty verification --------------------------------------------------------------------
def verify_duty(cid: int, candidates: list[str], sims: list[float], signals: dict,
                entails: list[float] | None = None) -> tuple:
    """Return (verdict, score, evidence_sentence, reason). `candidates`/`sims` are the top-k
    Stage-1 sentences (best first). `signals` carries deterministic crawl facts for structural duties.
    `entails`, when given, is the precomputed entailment probability per candidate (from one batched
    NLI pass in judge_all_verified) -- aligned to `candidates`; when None the propositional lane
    computes entailment lazily, one pair at a time."""
    # -- internal lane: not externally verifiable from a public site -> abstain to the engine
    if cid in INTERNAL:
        return ("Not disclosed", 0.0, "", "internal:not externally verifiable")

    # -- structural lane: decided by crawl signals, never by text similarity
    if cid in STRUCTURAL:
        ok = {
            33: signals.get("policy_found"),
            34: signals.get("cookie_policy"),
            35: signals.get("terms_found"),
            37: signals.get("contact_found"),
            38: signals.get("is_https"),
        }.get(cid)
        return ("Compliant" if ok else "Not disclosed", 1.0 if ok else 0.0,
                signals.get("evidence", {}).get(cid, ""), f"structural:{'present' if ok else 'absent'}")

    # -- content lane: substantive disclosure list, topically matched. DPO view: a clear substantive
    #    match is Compliant; a thinner on-topic match is a weak disclosure -> Partial, not full credit.
    if cid in CONTENT:
        for sent, sim in zip(candidates, sims):
            if _assertive(sent) and sim >= 0.45:
                return ("Compliant" if sim >= 0.60 else "Partial", round(sim, 3), sent,
                        f"content:assertive sim={sim:.2f}")
        return ("Not disclosed", 0.0, "", "content:no substantive disclosure")

    # -- propositional lane: a real assertive claim that either matches the duty strongly (topical)
    #    OR entails its legal test. Two signals, because NLI is brittle across paraphrases (a genuine
    #    retention clause can score sim 0.76 yet entail ~0), while similarity over-credits fragments
    #    (handled by the assertion gate above). Requiring assertive + (strong sim OR entail) gives
    #    both recall (paraphrase-robust) and precision (junk is non-assertive or off-topic).
    hyp = HYP.get(cid)
    best = ("Not disclosed", 0.0, "", "propositional:none")
    for i, (sent, sim) in enumerate(zip(candidates, sims)):
        if not _assertive(sent):
            continue
        if entails is not None:
            pe = entails[i] if i < len(entails) else 0.0
        else:
            pe = p_entail(sent, hyp) if hyp else 0.0
        # Compliant: a genuine commitment -- the sentence ENTAILS the legal test (topical similarity
        # alone is never compliance). A light sim floor keeps the entailment on-topic.
        if pe >= E_HIGH and sim >= SIM_FLOOR:
            return ("Compliant", round(max(sim, pe), 3), sent,
                    f"propositional:sim={sim:.2f} entail={pe:.2f}")
        # Partial: the duty is ADDRESSED but not clearly committed -- on-topic (S_PART) OR weakly
        # entailed (E_PART). This is the "weak but present" band the old AND-logic dropped into Gap.
        if (sim >= S_PART or pe >= E_PART) and best[0] == "Not disclosed":
            best = ("Partial", round(max(sim, pe), 3), sent,
                    f"propositional:sim={sim:.2f} entail={pe:.2f}")
    return best


def judge_all_verified(policy_text: str, signals: dict | None = None, topk: int = 3) -> dict:
    """Full two-stage judge: Stage-1 semantic retrieval + Stage-2 routed verification.
    Returns {cid: (verdict, score, evidence, reason)}.

    All propositional-lane entailment checks across every duty are gathered and run in ONE batched
    NLI pass (see p_entail_batch), so the Stage-2 cost is a single forward pass of <=~100 pairs
    rather than ~100 sequential ones."""
    from sentence_transformers import util
    from . import semantic as S
    signals = signals or {}
    sents = S._sentences(policy_text)
    if not sents:
        return {i: ("Not disclosed", 0.0, "", "no text") for i in S.EXEMPLARS}
    model = S._model()
    semb = model.encode(sents, convert_to_tensor=True, normalize_embeddings=True)

    # Stage-1: per-duty top-k candidate sentences by exemplar similarity.
    cand: dict[int, tuple[list[str], list[float]]] = {}
    for cid, ex_emb in S._EX_EMB.items():
        col = util.cos_sim(ex_emb, semb).max(dim=0).values      # best exemplar-sim per sentence
        k = min(topk, len(sents))
        idx = col.topk(k).indices.tolist()
        cand[cid] = ([sents[i] for i in idx], [float(col[i]) for i in idx])

    # Stage-2 (propositional lane): gather every assertive (candidate, hypothesis) pair across all
    # duties into one list, run a single batched NLI pass, then scatter the probabilities back.
    pairs: list[tuple[str, str]] = []
    loc: dict[int, list[int | None]] = {}      # loc[cid][j] = index into `pairs`, or None if skipped
    for cid, (cands, _sims) in cand.items():
        if cid in STRUCTURAL or cid in CONTENT or cid in INTERNAL:
            continue
        hyp = HYP.get(cid)
        if not hyp:
            continue
        row: list[int | None] = []
        for sent in cands:
            if _assertive(sent):
                row.append(len(pairs)); pairs.append((sent, hyp))
            else:
                row.append(None)
        loc[cid] = row
    probs = p_entail_batch(pairs) if pairs else []

    out = {}
    for cid, (cands, sims) in cand.items():
        entails = None
        if cid in loc:
            entails = [(probs[pi] if pi is not None else 0.0) for pi in loc[cid]]
        out[cid] = verify_duty(cid, cands, sims, signals, entails=entails)
    return out
