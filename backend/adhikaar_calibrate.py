"""
adhikaar_calibrate.py -- tune the semantic engine's thresholds against a labelled sentence set.

For each disclosure duty we hold realistic ways a real policy phrases it (POSITIVES) -- written
differently from the exemplars in semantic.py, to test generalisation, not memorisation. Each
positive is a NEGATIVE for every other duty. We score every (sentence, duty) pair with the semantic
engine, sweep the decision threshold, and report precision / recall / F1 so the threshold is chosen
from evidence, not guessed. We also flag duties whose exemplar separates positives from negatives
poorly (candidates for a better exemplar).

    python adhikaar_calibrate.py
"""
from __future__ import annotations
from app.rag import semantic

# duty id -> realistic disclosure sentences (labelled positives). Phrased unlike the exemplars.
GOLD: dict[int, list[str]] = {
    1: ["The information we gather from you includes your full name, contact number, e-mail and postal address.",
        "When you sign up we ask for your name, mobile number and date of birth."],
    2: ["We use the details you provide solely to fulfil your order and keep you informed about it.",
        "Your data is processed for the purpose of responding to your enquiry."],
    4: ["We rely on your consent as the legal ground for handling your information.",
        "Processing is carried out under a lawful basis recognised by the applicable law."],
    5: ["We ask only for the minimum information required to deliver the service you requested.",
        "Only data that is strictly necessary for the purpose is collected."],
    7: ["We make reasonable efforts to ensure the information we hold about you is correct and current.",
        "You can help us keep your records accurate by updating your details."],
    8: ["Records are kept for a period of seven years, after which they are securely destroyed.",
        "Once your data is no longer needed for the purpose, we delete it."],
    9: ["Your data is safeguarded using industry-standard encryption and strict access controls.",
        "We apply administrative and technical protections to keep your information secure."],
    10: ["Should a data breach occur, affected individuals and the regulator will be notified promptly.",
         "We will report any compromise of personal information to the Board and to you."],
    11: ["You are free to revoke your permission at any point through your account settings.",
         "Consent can be taken back as easily as it was given, by writing to us."],
    12: ["We obtain your explicit opt-in before processing; nothing is pre-selected on your behalf.",
         "You actively agree by ticking the box yourself."],
    13: ["You may route your consent preferences through a registered consent manager.",
         "A consent management platform is available to control your permissions."],
    14: ["A log of the permissions you have granted is available for you to inspect.",
         "You can review your consent history at any time."],
    15: ["For minors, we require confirmation from a parent or guardian before any processing.",
         "We do not profile or advertise to children and seek guardian approval first."],
    16: ["You can ask us for a copy of the personal information we hold about you.",
         "On request we will provide a summary of the data we process concerning you."],
    17: ["If any of your details are wrong, you may ask us to fix them.",
         "You have the ability to request rectification of inaccurate information."],
    18: ["You can request that we delete the personal data we hold about you.",
         "The right to have your information erased is available to you."],
    19: ["Complaints may be lodged with our nodal officer, who will resolve them within the stipulated time.",
         "If you are unhappy, escalate the matter to our grievance redressal contact."],
    20: ["You may appoint someone to act on your behalf in exercising these rights.",
         "A nominee can be designated to manage your data rights."],
    21: ["Questions about your privacy can be directed to privacy@company.com or our data officer.",
         "Reach our designated contact for any data-related concern at the address below."],
    24: ["We disclose your information to payment processors, delivery partners and analytics providers.",
         "The categories of recipients with whom we share data are listed here."],
    27: ["Some of your information may be handled by servers located outside the country.",
         "We may send your data abroad to our overseas service providers."],
    29: ["Your information is hosted in data centres located in Mumbai and Singapore.",
         "We store your records on cloud infrastructure in the regions named here."],
    33: ["This privacy statement is available from the footer of every page on our site.",
         "Our data-handling policy is published and can be read here."],
    34: ["We describe the cookies and tracking scripts used on our website.",
         "Details of the cookies we set are provided in this section."],
    35: ["Use of this website is governed by our terms and conditions.",
         "Please read the terms of use that apply to this service."],
    37: ["Our registered office is at 12 MG Road, Bengaluru, and our CIN is listed below.",
         "The company's registered address and corporate details are provided here."],
}
# generic sentences that should match NOTHING (hard negatives)
FILLER = [
    "Our mission is to make the internet safer for everyone.",
    "Founded in 2015, we are proud of our achievements and awards.",
    "Sign up for our newsletter to receive the latest updates and offers.",
    "Our team of volunteers works across twelve states in India.",
    "Donate today to support our cause and change lives.",
]


def main():
    if not semantic.available():
        print("sentence-transformers not installed."); return
    # build all (sentence, its true duty or None) and score against every duty's exemplar
    labelled = [(s, cid) for cid, sents in GOLD.items() for s in sents]
    labelled += [(s, None) for s in FILLER]
    duties = list(semantic.EXEMPLARS)

    # score matrix: for each sentence, judge_all treats it as the whole policy -> per-duty score
    print(f"scoring {len(labelled)} sentences x {len(duties)} duties ...")
    pairs = []                                            # (score, is_true_match)
    weak = {}                                             # duty -> (min positive score, max negative score)
    per_duty_pos = {c: [] for c in GOLD}
    for sent, true_cid in labelled:
        res = semantic.judge_all(sent, t_high=1.1, t_partial=1.1)   # thresholds irrelevant; want scores
        for cid in duties:
            score = res[cid][1]
            is_true = (cid == true_cid)
            if cid in GOLD:                              # only score duties we have labels for
                pairs.append((score, is_true))
                if is_true:
                    per_duty_pos[cid].append(score)

    # threshold sweep
    print("\nthresh  precision  recall   F1")
    best = (0, 0)
    for t in [x / 100 for x in range(25, 66, 2)]:
        tp = sum(1 for s, y in pairs if y and s >= t)
        fp = sum(1 for s, y in pairs if not y and s >= t)
        fn = sum(1 for s, y in pairs if y and s < t)
        prec = tp / (tp + fp) if tp + fp else 0
        rec = tp / (tp + fn) if tp + fn else 0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0
        if f1 > best[1]:
            best = (t, f1)
        print(f" {t:.2f}   {prec:6.2f}    {rec:5.2f}  {f1:5.2f}")
    print(f"\nBest F1 threshold: {best[0]:.2f} (F1 {best[1]:.2f})")

    # weak exemplars: positives that score low (< 0.40) -> exemplar doesn't capture the phrasing
    print("\nWeak duties (a labelled positive scored below 0.40 -> refine the exemplar):")
    for cid, scores in per_duty_pos.items():
        if scores and min(scores) < 0.40:
            print(f"  duty {cid}: positives {[round(s,2) for s in scores]}  req: {semantic.EXEMPLARS[cid][0][:50]}")


if __name__ == "__main__":
    main()
