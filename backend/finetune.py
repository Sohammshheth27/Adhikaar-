"""
finetune.py -- fine-tune the local semantic model on the REAL-policy corpus from build_corpus.py.

Inference in semantic.py scores each policy sentence by cosine to a per-duty exemplar. We fine-tune the
same bi-encoder so real disclosure sentences sit close to their duty's exemplar and unrelated sentences
sit far -- training directly on the (sentence, exemplar, label) pairs the LLM labelled from actual
policies. The tuned model saves locally; semantic.py loads it automatically when present, so the report
path stays identical (fast, offline, no API) but more accurate.

Self-contained manual training loop: needs only torch + sentence-transformers (no HF Trainer / datasets
/ accelerate), so it is robust across library versions.

    python finetune.py corpus.jsonl            # train, then it prints held-out metrics
    python calibrate.py                        # re-check thresholds on the tuned model

No synthetic text: every training sentence is copied verbatim from a crawled real policy.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from app.rag import semantic

OUT_DIR = Path(__file__).parent / "app" / "rag" / "models" / "adhikaar-minilm"


def _load(path: str):
    rows = [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
    ex = {cid: sents[0] for cid, sents in semantic.EXEMPLARS.items()}
    data = []
    for r in rows:
        anchor = ex.get(r["duty"])
        if anchor:
            data.append((r["sentence"], anchor, float(r["label"])))
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--val-frac", type=float, default=0.15)
    args = ap.parse_args()

    if not semantic.available():
        print("pip install sentence-transformers to fine-tune."); return

    import torch
    import torch.nn.functional as F
    from sentence_transformers import SentenceTransformer, util

    data = _load(args.corpus)
    if len(data) < 20:
        print(f"only {len(data)} pairs -- crawl more real policies with build_corpus.py first."); return

    cut = max(1, int(len(data) * (1 - args.val_frac)))
    train, val = data[:cut], data[cut:]
    print(f"{len(train)} train / {len(val)} val pairs (100% real-policy sentences)")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = SentenceTransformer("all-MiniLM-L6-v2", device=device)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr)

    def encode_grad(texts):
        feats = model.tokenize(texts)
        feats = {k: (v.to(device) if hasattr(v, "to") else v) for k, v in feats.items()}
        return model(feats)["sentence_embedding"]

    model.train()
    for epoch in range(args.epochs):
        import random
        random.shuffle(train)
        total = 0.0
        for i in range(0, len(train), args.batch):
            batch = train[i:i + args.batch]
            sents = [b[0] for b in batch]
            anchors = [b[1] for b in batch]
            labels = torch.tensor([b[2] for b in batch], device=device)
            ea = F.normalize(encode_grad(sents), p=2, dim=1)
            eb = F.normalize(encode_grad(anchors), p=2, dim=1)
            cos = (ea * eb).sum(dim=1)                 # cosine similarity per pair
            loss = F.mse_loss(cos, labels)            # push positives->1, negatives->0
            opt.zero_grad(); loss.backward(); opt.step()
            total += float(loss) * len(batch)
        print(f"epoch {epoch + 1}/{args.epochs}  loss {total / len(train):.4f}")

    OUT_DIR.parent.mkdir(parents=True, exist_ok=True)
    model.save(str(OUT_DIR))
    print(f"\nsaved fine-tuned model -> {OUT_DIR}")

    # held-out check: cosine on val pairs, best-F1 threshold
    if val:
        model.eval()
        with torch.no_grad():
            a = model.encode([v[0] for v in val], convert_to_tensor=True, normalize_embeddings=True)
            b = model.encode([v[1] for v in val], convert_to_tensor=True, normalize_embeddings=True)
        sims = util.pairwise_cos_sim(a, b)
        ys = torch.tensor([v[2] for v in val])
        best = (0.0, 0.0)
        for t in [x / 100 for x in range(30, 80, 2)]:
            pred = sims >= t
            tp = int(((pred == 1) & (ys == 1)).sum()); fp = int(((pred == 1) & (ys == 0)).sum())
            fn = int(((pred == 0) & (ys == 1)).sum())
            prec = tp / (tp + fp) if tp + fp else 0
            rec = tp / (tp + fn) if tp + fn else 0
            f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0
            if f1 > best[1]:
                best = (t, f1)
        print(f"held-out best F1 {best[1]:.2f} at threshold {best[0]:.2f} "
              f"(set semantic.T_HIGH near this; T_PARTIAL ~0.08 lower)")


if __name__ == "__main__":
    main()
