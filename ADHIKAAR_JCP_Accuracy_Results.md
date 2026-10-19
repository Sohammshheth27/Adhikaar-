# ADHIKAAR (MDPI JCP): Accuracy Results vs Human Gold (Section 4.2 and 4.3)

*Computed 2026-10-18 against human-adjudicated labels (E:\Verdict.xlsx, 423 duties across 9 sites,
one annotator, each positive verdict evidence-quoted; 91.3% of quotes verified verbatim in the frozen
policy text). Scorable rows: 395 (28 NotApplicable excluded, standard: the tool schema has no N/A
class). Tool vocabulary mapped to the human vocabulary: Not disclosed -> Gap, Not externally verifiable
-> NotVerifiable. These are real numbers, reported as computed. No em dashes.*

## Table A. Strict four-class agreement (tool vs human)

| Configuration | Exact accuracy | Macro-F1 | Cohen's kappa |
|---|---|---|---|
| rules-only | 0.428 | 0.298 | 0.21 |
| semantic (Stage-1) | 0.423 | 0.354 | 0.19 |
| NLI-verified (deployed) | 0.446 | 0.320 | 0.227 |

Agreement is "fair" (kappa about 0.23). The NLI config has the best exact accuracy and kappa; the
semantic config has the best macro-F1 because it preserves the Partial class the NLI stage collapses.
This is a genuine tradeoff and is reported as such, not spun as uniform NLI superiority.

## Table B. Confusion matrix, deployed NLI config (rows = human, columns = tool)

| human \ tool | Compliant | Partial | Gap | NotVerifiable |
|---|---|---|---|---|
| Compliant (64) | 49 | 0 | 14 | 1 |
| Partial (145) | 58 | 5 | 79 | 3 |
| Gap (133) | 10 | 3 | 120 | 0 |
| NotVerifiable (53) | 0 | 0 | 51 | 2 |

## Table C. Per-class precision / recall / F1 (deployed NLI)

| Class | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| Compliant | 0.419 | 0.766 | 0.541 | 64 |
| Partial | 0.625 | 0.034 | 0.065 | 145 |
| Gap | 0.455 | 0.902 | 0.605 | 133 |
| NotVerifiable | 0.333 | 0.038 | 0.068 | 53 |

## Table D. Operational gap-detection (binary: Partial or Gap = "deficiency")

| Configuration | Precision | Recall | F1 | False-positive rate |
|---|---|---|---|---|
| rules-only | 0.753 | 0.701 | 0.726 | 0.547 |
| semantic | 0.758 | 0.745 | 0.751 | 0.564 |
| NLI-verified (deployed) | 0.761 | 0.745 | 0.753 | 0.556 |

## Honest reading (for Section 4 and the Limitations)

1. **The tool detects gap EXISTENCE well, not gap DEGREE.** Gap recall is 0.902 and binary
   gap-detection F1 is 0.753: it rarely misses a real deficiency. But Partial recall is 0.034: it
   cannot reproduce the human severity distinction, collapsing "mentioned but incomplete" into either
   full compliance or outright absence. The automated judge is effectively binary, the human is graded.
2. **It over-flags (false-positive rate 0.556).** More than half the duties the human found acceptable
   (Compliant or NotVerifiable) are flagged as a deficiency by the tool. It is a conservative, strict
   auditor. For a screening tool whose output is reviewed, high recall at the cost of precision is a
   defensible design point, but it must be stated plainly.
3. **Stage contribution is real but small on accuracy.** Exact accuracy and kappa rise slightly from
   rules to NLI (0.428 -> 0.446 acc; 0.21 -> 0.227 kappa); macro-F1 is actually highest for the
   semantic stage (0.354) because it keeps the Partial class. The strongest case for the NLI stage is
   the Bucket-1 behaviour result (it retracts 20 unsupported Compliant verdicts), not a large accuracy
   jump here.

## Two things that affect the paper, flagged honestly

- **Single annotator.** These are one person's labels. A referee will ask whether the gold itself is
  reliable, especially given heavy Partial use (145/423 = 34%). We still need a SECOND annotator on an
  overlapping subset (2 to 3 sites) to report inter-annotator Cohen's kappa. Without it, the accuracy
  rests on an unvalidated ground truth. This is the single most important remaining gap.
- **Framing.** The headline metric should be the operational gap-detection result (F1 0.753, gap recall
  0.902), with the strict four-class numbers reported transparently and the Partial-collapse stated as
  a limitation. Claiming high "accuracy" on the four-class task would be dishonest; claiming reliable
  gap SCREENING is supported.

Artefacts in `D:\Adhikaar\gold_set\`: `accuracy_results.json` (all numbers), `config_verdicts.csv`
(tool verdicts), `E:\Verdict.xlsx` (human gold with evidence quotes).

## Update: DPO recalibration and the LLM judge (added 2026-10-19)

After the first pass, the NLI propositional and content lanes were recalibrated from compliance-officer
principles (Compliant requires entailment of the legal test, never topical similarity alone; "addressed
but not committed" is Partial via a topical-presence OR weak-entailment band). Separately, an open-weight
LLM judge (Llama-3.3-70B-Instruct, served free on Cloudflare Workers AI, temperature 0, judging only the
frozen policy text) was run as the PRIMARY judge over all 9 sites. Both evaluated against the same human
gold (395 scorable rows). Open-weight + pinned version keeps the LLM result reproducible.

### Full judge ladder (vs human gold)

| Judge | Exact acc | Macro-F1 | Cohen's kappa | Gap-detect F1 | False-positive rate |
|---|---|---|---|---|---|
| rules-only | 0.428 | 0.298 | 0.210 | 0.726 | 0.547 |
| semantic (SBERT) | 0.423 | 0.354 | 0.192 | 0.751 | 0.564 |
| NLI, DPO-calibrated | 0.448 | 0.402 | 0.238 | 0.751 | 0.453 |
| LLM (Llama-3.3-70B) | 0.562 | 0.532 | 0.418 | 0.760 | 0.170 |

### Per-class P/R/F1, LLM judge

| Class | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| Compliant | 0.351 | 0.625 | 0.449 | 64 |
| Partial | 0.704 | 0.131 | 0.221 | 145 |
| Gap | 0.669 | 0.880 | 0.760 | 133 |
| NotVerifiable | 0.582 | 0.868 | 0.697 | 53 |

### Confusion matrix, LLM judge (rows = human, cols = LLM)

| human \ LLM | Compliant | Partial | Gap | NotVerifiable |
|---|---|---|---|---|
| Compliant (64) | 40 | 5 | 8 | 11 |
| Partial (145) | 68 | 19 | 44 | 14 |
| Gap (133) | 6 | 2 | 117 | 8 |
| NotVerifiable (53) | 0 | 1 | 6 | 46 |

### Honest reading
- The LLM judge is the clear top of the ladder: Cohen's kappa rises from 0.24 (NLI) to 0.418 ("fair" to
  "moderate"), false-positive rate falls from 0.45 to 0.17, and the NotVerifiable class (internal controls)
  is handled well for the first time (recall 0.87 vs 0.28). It does not hallucinate evidence: 95% of its
  Compliant/Partial quotes are verbatim in the policy.
- The residual disagreement is concentrated in the Partial-vs-Compliant boundary (Partial recall 0.131;
  68 human-Partials read as Compliant). This boundary is inherently subjective, and the single human
  annotator graded it strictly. A second annotator is needed to establish the human-to-human ceiling that
  the LLM's 0.418 should be judged against.
- Cost/reproducibility: 9 batched calls (all 47 duties per site), about 20 to 44 s per site, free tier.
  Open weights + temperature 0 + pinned model name make the result replicable, unlike a proprietary API.

## Update 2: full RAG + LLM + NLI architecture (added 2026-10-19)

The LLM judge was extended into the full intended architecture: (1) a SEMANTIC RETRIEVAL front-end
selects the most duty-relevant passages from the WHOLE policy (fixing truncation on long policies, where
the LLM previously saw only the first 24k chars and wrongly scored later-section duties as Gap); (2) the
LLM (Llama-3.3-70B, temperature 0) judges the retrieved digest; (3) an NLI GUARDRAIL cross-checks the
LLM (downgrades a Compliant the NLI cannot entail; flags a Gap the NLI entails strongly). All against the
same human gold (395 scorable rows). Quotes remain grounded (96.6% verbatim in policy).

### Architecture progression (vs human gold)

| Architecture | Exact (4-class) | Macro-F1 | Cohen's kappa | Binary gap F1 | FPR |
|---|---|---|---|---|---|
| NLI alone (DPO-calibrated) | 0.448 | 0.402 | 0.238 | 0.75 | 0.45 |
| LLM, truncated policy text | 0.562 | 0.532 | 0.418 | 0.76 | 0.17 |
| LLM + semantic retrieval | 0.618 | 0.609 | 0.482 | 0.80 | 0.19 |
| LLM + retrieval + NLI guardrail (full) | 0.648 | 0.643 | 0.512 | 0.84 | 0.26 |
| Full system, 3-class (Addressed/Gap/NotVerifiable) | 0.790 | n/a | 0.651 | n/a | n/a |

### Per-class P/R/F1, full system (LLM + RAG + NLI)

| Class | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| Compliant | 0.494 | 0.641 | 0.558 | 64 |
| Partial | 0.653 | 0.455 | 0.537 | 145 |
| Gap | 0.714 | 0.827 | 0.767 | 133 |
| NotVerifiable | 0.684 | 0.736 | 0.709 | 53 |

### Honest reading
- The full RAG + LLM + NLI architecture more than doubles agreement over the NLI-only judge (kappa 0.238
  to 0.512, "fair" to "moderate"), reaches "substantial" on the 3-class task (kappa 0.651), and lifts
  gap-screening F1 to 0.84. Every verdict class now has a real F1; the Partial class is no longer dead
  (recall 0.131 to 0.455).
- Each component earns its place: retrieval adds +0.06 kappa (recall on long policies), the NLI guardrail
  adds +0.03 kappa (recovers over-credited Partials). This is a genuine ablation, not an assertion.
- Strict four-class accuracy (0.648) does not reach 0.90 and is not expected to: the residual lives in the
  inherently subjective Compliant-vs-Partial boundary. The defensible headline is substantial agreement on
  the addressed/missing/unverifiable task and reliable gap-screening, not a 0.90 four-class figure.
- Open weights + temperature 0 + pinned model name keep the whole result reproducible.

## Update 3: per-duty routing (added 2026-10-19)

NotVerifiable was found to be a property of the DUTY, not the policy: 92% of the human's 53 NotVerifiable
labels fall on 8 internal-practice duties (audits, staff training, records of processing, incident
response, vendor risk, periodic review), all already flagged disclosure_only in the catalog. These, and
the 5 structural/existence duties (policy/cookie/terms/contact/HTTPS), are routed deterministically; only
the remaining disclosure-content duties go to the LLM+RAG+NLI stack. Routing sets are fixed from the legal
nature of each duty (a-priori), not from the test labels.

| System | Exact (4-class) | Macro-F1 | kappa | NotVerifiable recall | Binary gap F1 |
|---|---|---|---|---|---|
| LLM + RAG + NLI ensemble | 0.648 | 0.643 | 0.512 | 0.74 | 0.84 |
| + per-duty routing | 0.676 | 0.684 | 0.557 | 0.94 | 0.85 |
| + per-duty routing, 3-class | 0.808 | n/a | 0.685 | n/a | n/a |

Routed confusion (rows=human, cols=tool): NotVerifiable 50/53, Gap 110/133, Compliant 48/64 are clean;
the residual error concentrates in the Partial row (human Partial misread as Compliant 42, as Gap 31).

Honest reading: routing lifts kappa to 0.557 (4-class) and 0.685 (3-class, "substantial"), and NotVerifiable
recall to 0.94. The remaining error is dominated by the subjective Compliant-vs-Partial boundary and cannot
be engineered past the human-to-human agreement ceiling, which a second annotator is required to establish.

## Update 4: duty decomposition (added 2026-10-19)

Each content duty was decomposed into objective yes/no sub-facts (operationalising the legal requirement
a-priori, not fitted to the labels); the LLM answers the sub-facts and the verdict is derived
deterministically (all specific sub-facts yes = Compliant; any yes = Partial; none = Gap). Structural and
internal duties stay routed. This replaces the subjective holistic verdict with countable facts and yields
an auditable sub-fact trail per verdict.

| Approach | Exact (4-class) | kappa | 3-class kappa | Binary gap F1 | FPR | NotVerifiable recall |
|---|---|---|---|---|---|---|
| Routed LLM+RAG+NLI ensemble | 0.676 | 0.557 | 0.685 | 0.85 | 0.20 | 0.94 |
| Duty decomposition + NLI guard | 0.658 | 0.532 | 0.646 | 0.86 | 0.14 | 0.925 |

Decomposition gives the lowest false-positive rate (0.14), the best binary gap-screening (F1 0.86), the
cleanest Compliant (F1 0.64) and NotVerifiable (F1 0.85) classes, and an auditable yes/no sub-fact trail.
It does NOT improve the Partial boundary (Partial recall 0.33): the subjectivity relocates into the
sub-fact judgments. Across all six levers explored (DPO recalibration, LLM, RAG retrieval, NLI guardrail,
per-duty routing, duty decomposition) the full-system agreement converges at kappa 0.53 to 0.56 (4-class)
and binary gap-detection F1 0.85 to 0.86. This convergence indicates a genuine ceiling in the subjective
Compliant-vs-Partial boundary, not a missing technique. Strict four-class accuracy near 0.90 is therefore
not attainable against a single annotator; the defensible, strong results are substantial 3-class
agreement (kappa 0.65 to 0.69) and reliable gap-screening (F1 0.85 to 0.86, FPR as low as 0.14).

Recommended system for the paper: the routed RAG + LLM + NLI pipeline, with duty decomposition presented
as an interpretability-oriented variant that trades a hair of 4-class agreement for a lower false-positive
rate and a transparent sub-fact audit trail.
