# ADHIKAAR (MDPI JCP): Bucket 1 Ablation (label-free behaviour deltas)

*Ran 2026-10-18 over the 9 gold-set sites (3 EDU, 3 NGO, 3 SME), all 47 DPDP duties, three judge
configurations. The LLM overlay is OFF (optional, upgrade-only): the system under test is the real
deployed pipeline, rules then semantic then NLI-verified. No human labels are used here, so these are
behaviour deltas (how the verdict changes as stages are added), not accuracy. Accuracy (per-control
P/R/F1, macro-F1, false-positive rate) is computed from the same frozen verdicts once the human gold
labels are filled, joining on (site, duty_id). No em dashes.*

Configurations:
- **rules**: keyword/signal matching only (no model in the verdict path).
- **semantic**: Stage-1 SBERT sentence matching (cosine thresholded).
- **nli**: Stage-2 verified judge (NLI entailment over the retrieved sentence; the deployed default).

Total judgements: 9 sites x 47 duties x 3 configs = 1,269.

## Table A. Verdict distribution by configuration (out of 423 duty judgements each)

| Verdict | rules | semantic | nli (deployed) |
|---|---|---|---|
| Compliant | 128 | 101 | 117 |
| Partial | 2 | 57 | 8 |
| Not disclosed | 285 | 241 | 292 |
| Not externally verifiable | 8 | 24 | 6 |

Reading: keyword matching (rules) almost never produces Partial (2) and over-commits to Compliant on
mere term presence. Semantic matching surfaces nuance (57 Partial) but over-credits topically similar
marketing text. NLI entailment collapses the vague middle (Partial 57 to 8): a claim is either entailed
by a real commitment (Compliant) or it is not (Not disclosed).

## Table B. What NLI entailment changes, relative to semantic (semantic -> nli transitions)

| Transition | Count | Interpretation |
|---|---|---|
| Not disclosed -> Not disclosed | 229 | stable true negatives |
| Compliant -> Compliant | 80 | stable positives (entailment confirms) |
| Partial -> Compliant | 27 | entailment promotes a genuine commitment semantic left vague |
| Partial -> Not disclosed | 25 | entailment rejects a non-committal partial |
| Compliant -> Not disclosed | 20 | entailment RETRACTS a topically similar but unsupported finding |
| Not externally verifiable -> Not disclosed | 18 | reclassified when no entailed disclosure exists |
| Not disclosed -> Compliant | 10 | entailment recovers a disclosure semantic missed |

Net: **156 of 423 duties (36.9%) receive a different verdict across the three tiers**, so the stages are
far from redundant. Entailment verification moves 45 verdicts DOWN (20 Compliant and 25 Partial retracted
as unsupported) and 37 UP (27 + 10 confirmed), i.e. it is stricter on unsupported positive claims while
still recovering real disclosures. This is the "NLI reduces unsupported findings" behaviour, shown
directly rather than asserted.

## Evidence grounding

Of the 125 positive (Compliant or Partial) verdicts the deployed NLI judge emits, **89 (71.2%) carry a
verbatim entailed sentence** as evidence. The remainder are existence/structural duties (for example
HTTPS, policy-document presence) decided from observed facts rather than policy prose, so they carry no
quote by design. This is the evidence-grounding rate for Section 4.5; its quality (whether the quoted
sentence actually supports the duty) is adjudicated against the human labels.

## Latency (per site, mean over 9 sites)

| Stage | Mean time per site |
|---|---|
| Semantic build (SBERT over whole-site text) | 2.34 s |
| NLI verify build (entailment, top-k per duty) | 14.35 s |

NLI verification costs about 6x the semantic stage. This is the accuracy/latency tradeoff for the cost
discussion: entailment is the expensive stage, and it is what prevents marketing copy from scoring as a
disclosure. No API/token cost applies (the LLM overlay is off).

## What this feeds, and the honest boundary

- Section 4.3 (ablation): Table A and Table B as behaviour deltas now; the same rows become accuracy
  deltas (does each stage move verdicts toward the human truth?) once labels are filled.
- Section 4.4 (operational): the latency table above.
- Section 4.5 (evidence grounding): the 71.2% grounding rate; quality pending labels.

Frozen artefacts in `D:\Adhikaar\gold_set\`: `config_verdicts.csv` (per-site, per-duty verdicts under all
three configs, the join key for accuracy), `ablation_summary.json` (these aggregates). Whether the 20
retractions and 37 promotions are CORRECT is exactly what the gold labels decide; that is not claimed here.
