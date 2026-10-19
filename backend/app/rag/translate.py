"""translate.py -- machine-translate the dynamic report fields into an Indian language.

Output-side multilingual support: the judging pipeline stays in English (so accuracy and the
validated thresholds are untouched); only the human-readable report prose is translated for display.
Quoted policy clauses (evidence) and statutory citations are kept in the ORIGINAL language, exactly as
the frontend i18n note promises. Translations are cached per language on disk, so repeated strings
(the fixed duty catalogue, the templated findings) cost nothing after the first scan in a language.
"""
from __future__ import annotations
import json
import re
from copy import deepcopy
from pathlib import Path

from . import llm_judge

_CACHE_DIR = Path(__file__).resolve().parent / "i18n_cache"
_CACHE_DIR.mkdir(exist_ok=True)

# locale -> (base code, language name for the translation prompt)
_LANGS = {
    "hi": "Hindi", "mr": "Marathi", "bn": "Bengali", "ta": "Tamil", "te": "Telugu",
    "gu": "Gujarati", "kn": "Kannada", "ml": "Malayalam", "pa": "Punjabi", "or": "Odia",
    "as": "Assamese", "ur": "Urdu",
}


def _base(lang: str) -> str:
    return (lang or "").strip().lower().split("-")[0]


def is_supported(lang: str) -> bool:
    """True when lang is a non-English Indian language we translate into (and the LLM is available)."""
    return _base(lang) in _LANGS and llm_judge.enabled()


def _cache_path(lang: str) -> Path:
    return _CACHE_DIR / (_base(lang) + ".json")


def _load_cache(lang: str) -> dict:
    p = _cache_path(lang)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_cache(lang: str, cache: dict) -> None:
    try:
        _cache_path(lang).write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
    except Exception:
        pass


_SYS = ("You are a professional legal translator. Translate each numbered English item into {lang}. "
        "Keep statute references and short codes recognizable (for example 'Section 5', 'Rule 3', "
        "'DPDP', 'IT Act', 'HTTPS', grade letters A-E). Do not add any commentary or notes. Return "
        "exactly the same numbered list, one item per line, nothing else.")


def _translate_batch(strings: list[str], lang: str):
    """One LLM call translating a numbered batch. Returns the translated list, or None if the call
    failed (so the caller does not cache a failed, English-passthrough result)."""
    name = _LANGS[_base(lang)]
    numbered = "\n".join(f"{i+1}. {s}" for i, s in enumerate(strings))
    try:
        raw = llm_judge._call_openai(_SYS.format(lang=name), numbered)
    except Exception:
        return None
    out: dict[int, str] = {}
    for line in raw.splitlines():
        m = re.match(r"\s*(\d+)[.)]\s*(.*\S)\s*$", line)
        if m:
            idx = int(m.group(1)) - 1
            if 0 <= idx < len(strings):
                out[idx] = m.group(2)
    return [out.get(i) or strings[i] for i in range(len(strings))]


def translate_strings(strings: list[str], lang: str) -> dict:
    """Return {original -> translation} for the unique non-empty strings, using and updating the cache.
    Only genuine translations are cached; a failed or passthrough result is never stored, so a transient
    rate limit cannot permanently pin a string to its English original."""
    uniq = [s for s in dict.fromkeys(strings) if s and s.strip()]
    if not uniq:
        return {}
    cache = _load_cache(lang)
    missing = [s for s in uniq if s not in cache]
    wrote = False
    for i in range(0, len(missing), 40):                  # batch to keep each prompt bounded
        chunk = missing[i:i + 40]
        res = _translate_batch(chunk, lang)
        if res is None:                                   # call failed -> leave uncached, retry next time
            continue
        for src, dst in zip(chunk, res):
            if dst and dst != src:                        # cache only a real translation
                cache[src] = dst
                wrote = True
    if wrote:
        _save_cache(lang, cache)
    return {s: cache.get(s, s) for s in uniq}


# Report fields that carry human-readable prose (translate) vs. fields kept verbatim
# (evidence quote, statutory citation/anchor, URLs, verdict enums handled by the UI's static i18n).
def translate_report(report: dict, lang: str) -> dict:
    """Return a copy of the UI report with its prose translated into lang; evidence and citations
    stay in the original. No-op (returns the report unchanged) when lang is English or unsupported."""
    if not is_supported(lang):
        return report
    rep = deepcopy(report)

    pool: list[str] = []
    for c in rep.get("checks", []) or []:
        pool += [c.get("title", ""), c.get("finding", ""), c.get("fix") or ""]
    for d in rep.get("duties", []) or []:
        pool += [d.get("requirement", ""), d.get("category", "")]
    if isinstance(rep.get("risk"), dict):
        pool.append(rep["risk"].get("summary", ""))

    tmap = translate_strings(pool, lang)

    def tr(s):
        return tmap.get(s, s) if s else s

    for c in rep.get("checks", []) or []:
        c["title"] = tr(c.get("title", ""))
        c["finding"] = tr(c.get("finding", ""))
        if c.get("fix"):
            c["fix"] = tr(c["fix"])
    for d in rep.get("duties", []) or []:
        d["requirement"] = tr(d.get("requirement", ""))
        d["category"] = tr(d.get("category", ""))
    if isinstance(rep.get("risk"), dict):
        rep["risk"]["summary"] = tr(rep["risk"].get("summary", ""))

    rep["translated_into"] = _base(lang)
    rep["translation_note"] = ("Machine-translated from the English source. Quoted clauses and "
                               "statutory citations remain in the original.")
    return rep
