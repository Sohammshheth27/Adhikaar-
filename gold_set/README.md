# ADHIKAAR Accuracy Gold Set (blind human adjudication)

Purpose: an independent, human-adjudicated ground truth for the 47 DPDP duties, used to
measure Adhikaar's accuracy in Section 4.2 and 4.3 of the paper. The tool's own verdicts
are deliberately NOT included here, so the human labels stay independent and the accuracy
comparison is not circular.

## What to do
1. Read `RUBRIC.md` (the 47 duties, their statutory anchors, and the five allowed verdicts).
2. For each site, open its frozen policy text: `policy_<sector>_<site>.txt`.
3. In `gold_labels_blank.csv`, fill the `verdict` column for each of the 47 duties, judging
   ONLY from the policy text and the statute. Optionally record the supporting sentence in
   `evidence_note`. Do not consult the Adhikaar output.

Verdicts: Compliant / Partial / Gap / NotApplicable / NotVerifiable (see RUBRIC.md).

## Composition (9 sites, 3 per sector, 423 label rows)
- EDU: jnu.ac.in, du.ac.in, iima.ac.in
- NGO: savethechildren.in, akshayapatra.org, tatatrusts.org
- SME: powersoft.in (case study), networkintelligence.ai (case study), robu.in

Each kept site has substantial, JS-rendered or static policy text (frozen on 2026-10-18).

## Excluded, and why (recorded as a finding, not labeled)
These sites had no reachable public privacy policy at crawl time and are therefore not part
of the labeled accuracy set:
- iitb.ac.in: only a generic website-policy page, no privacy-notice terms.
- childrightsandyou.org: /privacy-policy returns 404.
- glen-india.com: /privacy-policy returns 404.
- sudarshanpharma.com: TLS certificate does not cover the hostname (ERR_SSL_UNRECOGNIZED_NAME).
- veefin.com: /privacy-policy renders a JS shell with no policy body.
Their stub `policy_*.txt` files are kept as evidence of the no-policy finding.

## Inter-annotator agreement (Cohen's kappa)
For kappa, a second rater (e.g. Dr. Nilakshi Jain) should independently label an overlapping
subset, ideally 2 to 3 sites across sectors (about 94 to 141 rows), using the same RUBRIC.md
and the same frozen policy text, without seeing the first rater's labels.

## After labeling
Return the filled `gold_labels_blank.csv` (and any second-rater copy). The analysis will then
compute per-control precision/recall/F1, macro-F1, Cohen's kappa (Table 2), the rules-only vs
single-LLM vs full-Adhikaar baseline (Table 3), the ablation (Table 4), and evidence-grounding
quality (Table 5).
