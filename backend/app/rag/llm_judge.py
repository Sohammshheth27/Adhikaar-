"""
llm_judge.py -- LLM disclosure judge (highest-accuracy layer AND the labeller for fine-tuning).

Given a REAL policy text, an LLM decides, for each of the 47 DPDP duties, whether the policy
discloses it (Compliant / Partial / Not disclosed) and returns the VERBATIM sentence that supports
the verdict. Citation integrity is enforced: the model is instructed to judge only from the supplied
text and to quote evidence verbatim; any "evidence" that is not a substring of the policy is dropped
to empty (so a hallucinated quote can never appear in a report).

Configuration (no keys are stored in code):
    ADHIKAAR_LLM_PROVIDER = anthropic | openai        (default anthropic)
    ADHIKAAR_LLM_API_KEY  = <your key>                (required to run)
    ADHIKAAR_LLM_MODEL    = model id                  (sensible default per provider)

Used two ways:
    * inference  -- engine calls judge_policy() when ADHIKAAR_LLM_JUDGE=1 and a key is set.
    * labelling  -- build_corpus.py calls judge_policy() to label a corpus of real policies.
"""
from __future__ import annotations
import os
import re
import json

from ..compliance.catalog import CHECKS

_VERDICTS = {"Compliant", "Partial", "Not disclosed"}
_VERDICTS4 = {"Compliant", "Partial", "Gap", "NotVerifiable"}


def _load_env_file() -> None:
    """Load credentials from backend/.llm_env (untracked) into the environment if present, so the
    deployed server picks up the LLM judge config without a manual export. Never overrides an
    already-set variable."""
    try:
        p = os.path.join(os.path.dirname(__file__), "..", "..", ".llm_env")
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip())
    except Exception:
        pass


_load_env_file()


def enabled() -> bool:
    on = os.environ.get("ADHIKAAR_LLM_JUDGE", "").strip() in ("1", "true", "yes")
    return on and (bool(_key()) or bool(_base_url_env()))


def _base_url_env() -> str:
    return os.environ.get("ADHIKAAR_LLM_BASE_URL", "").strip().rstrip("/")


def _base_url() -> str:
    return _base_url_env() or "https://api.openai.com/v1"


def _key() -> str:
    return os.environ.get("ADHIKAAR_LLM_API_KEY", "").strip()


def _provider() -> str:
    return os.environ.get("ADHIKAAR_LLM_PROVIDER", "anthropic").strip().lower()


def _model() -> str:
    m = os.environ.get("ADHIKAAR_LLM_MODEL", "").strip()
    if m:
        return m
    return "claude-sonnet-5" if _provider() == "anthropic" else "gpt-4o-mini"


def _requirement_block() -> str:
    lines = []
    for c in CHECKS:
        lines.append(f'{c["id"]}. {c["requirement"]}')
    return "\n".join(lines)


_SYSTEM = (
    "You are a meticulous data-protection compliance analyst assessing an organisation's published "
    "privacy notice against India's DPDP Act 2023 and DPDP Rules 2025. You judge ONLY from the policy "
    "text provided. You never infer a disclosure that is not present, and you never invent quotes. For "
    "each requirement return a verdict and, when Compliant or Partial, the single most relevant VERBATIM "
    "sentence copied exactly from the policy. If a requirement is not addressed, verdict 'Not disclosed' "
    "and empty evidence. 'Partial' means addressed but incomplete or vague. Output strict JSON only."
)


def _prompt(policy_text: str) -> str:
    return (
        "Requirements (id. text):\n" + _requirement_block() +
        "\n\nPolicy text:\n\"\"\"\n" + policy_text[:20000] + "\n\"\"\"\n\n"
        "Return a JSON object mapping each requirement id (as a string) to "
        '{"verdict": "Compliant"|"Partial"|"Not disclosed", "evidence": "<verbatim sentence or empty>"}. '
        "JSON only, no prose."
    )


def _retry_after(e, default: float) -> float:
    """Honor the server's own retry hint: Retry-After header or a 'retry in Xs' note in the body."""
    try:
        ra = e.response.headers.get("retry-after")
        if ra:
            return min(90.0, float(ra) + 1)
    except Exception:
        pass
    try:
        m = re.search(r"retry in ([0-9.]+)s", e.response.text)
        if m:
            return min(90.0, float(m.group(1)) + 2)
    except Exception:
        pass
    return default


def _retry(fn, attempts: int = 6):
    """Retry transient network/5xx/429 failures. For 429 (rate limit) wait the delay the API asks for,
    instead of burning fast retries -- that is what caused the free-tier quota cascade."""
    import time
    import httpx
    last = None
    for i in range(attempts):
        try:
            return fn()
        except (httpx.TransportError, httpx.RemoteProtocolError, httpx.TimeoutException) as e:
            last = e
            time.sleep(2 * (i + 1))
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            if code < 500 and code != 429:
                raise                                # 4xx (bad model/key) won't fix itself
            last = e
            time.sleep(_retry_after(e, 2 * (i + 1)) if code == 429 else 2 * (i + 1))
    raise last


def _call_anthropic(system: str, user: str) -> str:
    import httpx

    def _do():
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": _key(), "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": _model(), "max_tokens": _maxtok(), "system": system,
                  "messages": [{"role": "user", "content": user}]},
            timeout=120,
        )
        r.raise_for_status()
        return "".join(b.get("text", "") for b in r.json().get("content", []))
    return _retry(_do)


def _maxtok() -> int:
    # 16000 by default: the 47-duty JSON with verbatim evidence needs headroom or it truncates.
    try:
        return max(512, int(os.environ.get("ADHIKAAR_LLM_MAXTOK", "16000")))
    except ValueError:
        return 16000


def _call_openai(system: str, user: str) -> str:
    import httpx
    key = _key() or "not-needed"                 # local servers (e.g. Ollama) accept any token

    def _do():
        payload = {"model": _model(), "temperature": 0, "max_tokens": _maxtok(),
                   "messages": [{"role": "system", "content": system},
                                {"role": "user", "content": user}]}
        # Reasoning models (e.g. Groq gpt-oss) spend the token budget on hidden reasoning and can
        # emit zero answer tokens; a raised max_tokens + low reasoning effort leaves room for the JSON.
        eff = os.environ.get("ADHIKAAR_LLM_REASONING", "").strip()
        if eff:
            payload["reasoning_effort"] = eff
        r = httpx.post(
            _base_url() + "/chat/completions",
            headers={"Authorization": f"Bearer {key}", "content-type": "application/json"},
            json=payload,
            timeout=180,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    return _retry(_do)


def _extract_json(s: str) -> dict:
    m = re.search(r"\{.*\}", s, re.S)
    if not m:
        return {}
    blob = m.group(0)
    try:
        return json.loads(blob)
    except Exception:
        # Salvage a truncated response: keep every complete '"id": { ... }' entry we can parse.
        out = {}
        for mm in re.finditer(r'"(\d+)"\s*:\s*(\{[^{}]*\})', blob):
            try:
                out[mm.group(1)] = json.loads(mm.group(2))
            except Exception:
                continue
        return out


_SYSTEM_RAG = (
    "You are an experienced Data Protection Officer auditing an organisation's PUBLISHED privacy "
    "notice against India's DPDP Act 2023 and DPDP Rules 2025. Judge ONLY from the policy text "
    "provided. Never infer a disclosure that is not present; never invent a quote. For each "
    "requirement assign exactly one verdict:\n"
    "  Compliant = the policy CLEARLY COMMITS to / satisfies the requirement (a specific, concrete "
    "statement, not a vague gesture).\n"
    "  Partial = the topic is ADDRESSED but the statement is vague, incomplete, or conditional.\n"
    "  Gap = the requirement is expected but is ABSENT from the policy.\n"
    "  NotVerifiable = an INTERNAL control that cannot be confirmed from public policy text.\n"
    "For Compliant or Partial, give the single most relevant VERBATIM sentence copied exactly from "
    "the policy; otherwise empty. Output STRICT JSON only, no markdown, no prose."
)


def _rag_digest(policy_text: str, topk: int = 4, floor: float = 0.22, cap: int = 24000) -> str:
    """Semantic retrieval front-end: return the most duty-relevant passages from the WHOLE policy,
    so a long policy is not truncated to its first N chars before the LLM sees it. Falls back to a
    plain prefix when the sentence-transformer is unavailable."""
    try:
        from . import semantic as S
        if not S.available():
            return (policy_text or "")[:cap]
        from sentence_transformers import util
        parts = re.split(r"(?<=[.!?])\s+|\n+|•|\|", policy_text or "")
        sents, seen = [], set()
        for p in parts:
            p = re.sub(r"\s+", " ", p).strip()
            if 15 <= len(p) <= 400 and p.lower() not in seen:
                seen.add(p.lower()); sents.append(p)
            if len(sents) >= 4000:
                break
        if not sents:
            return (policy_text or "")[:cap]
        model = S._model()
        emb = model.encode(sents, convert_to_tensor=True, normalize_embeddings=True, batch_size=128)
        chosen = set()
        for cid, ex in S._EX_EMB.items():
            col = util.cos_sim(ex, emb).max(dim=0).values
            for j in col.argsort(descending=True).tolist()[:topk]:
                if float(col[j]) >= floor:
                    chosen.add(j)
        return "\n".join(sents[j] for j in sorted(chosen))[:cap]
    except Exception:
        return (policy_text or "")[:cap]


def _prompt_rag(ctx: str) -> str:
    return ("Requirements (id. text):\n" + _requirement_block() +
            "\n\nMost relevant policy passages (retrieved from the full policy):\n\"\"\"\n" + ctx +
            "\n\"\"\"\n\n"
            'Return a JSON object mapping each requirement id (string) to '
            '{"verdict":"Compliant"|"Partial"|"Gap"|"NotVerifiable","evidence":"<verbatim or empty>"}. '
            "All ids must be present. JSON only, no prose.")


def judge_policy_rag(policy_text: str) -> dict[int, tuple[str, str]]:
    """Deployed primary judge: semantic-retrieval digest + LLM, 4-verdict scheme
    (Compliant / Partial / Gap / NotVerifiable). Returns {check_id: (verdict4, verbatim_evidence)}.
    Same citation guard as judge_policy: a quote not verbatim in the policy is dropped, and a
    Compliant with no valid quote is softened to Partial."""
    if not (policy_text or "").strip():
        return {}
    if not _key() and not _base_url_env():
        return {}
    ctx = _rag_digest(policy_text)
    raw = (_call_anthropic if _provider() == "anthropic" else _call_openai)(_SYSTEM_RAG, _prompt_rag(ctx))
    data = _extract_json(raw)
    low = (policy_text or "").lower()
    out: dict[int, tuple[str, str]] = {}
    for c in CHECKS:
        item = data.get(str(c["id"])) or data.get(c["id"]) or {}
        v = item.get("verdict", "Gap")
        if v not in _VERDICTS4:
            v = {"Not disclosed": "Gap", "Not externally verifiable": "NotVerifiable"}.get(v, "Gap")
        ev = (item.get("evidence") or "").strip()
        if ev and ev.lower() not in low:
            ev = ""
            if v == "Compliant":
                v = "Partial"
        out[c["id"]] = (v, ev)
    return out


def judge_policy(policy_text: str) -> dict[int, tuple[str, str]]:
    """Return {check_id: (verdict, verbatim_evidence)} for the whole policy in one call.

    Citation guard: any evidence not found verbatim (case-insensitive) in the policy is blanked, and
    an evidence-bearing verdict with no valid quote is downgraded so nothing unsupported is asserted.
    """
    if not (policy_text or "").strip():
        return {}
    if not _key() and not _base_url_env():
        return {}
    raw = (_call_anthropic if _provider() == "anthropic" else _call_openai)(_SYSTEM, _prompt(policy_text))
    data = _extract_json(raw)
    low = (policy_text or "").lower()
    out: dict[int, tuple[str, str]] = {}
    for c in CHECKS:
        item = data.get(str(c["id"])) or data.get(c["id"]) or {}
        verdict = item.get("verdict", "Not disclosed")
        if verdict not in _VERDICTS:
            verdict = "Not disclosed"
        ev = (item.get("evidence") or "").strip()
        if ev and ev.lower() not in low:               # guard: quote must be verbatim from the policy
            ev = ""
            if verdict == "Compliant":                 # no valid quote -> do not assert full compliance
                verdict = "Partial"
        out[c["id"]] = (verdict, ev)
    return out
