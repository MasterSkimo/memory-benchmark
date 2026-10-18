"""Train the V2 bilingual neural baseline from public authored dev pairs."""
from __future__ import annotations
import hashlib, json, random, re
from pathlib import Path
import numpy as np
import torch
from torch import nn
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[3]
DATA = Path(__file__).with_name("dev-pairs.jsonl")
OUT = ROOT / ".models/v2/trained-multilingual"
SEED = 20261018
DIM = 384
TOKEN = re.compile(r"[^\W_]+", re.UNICODE)


def tokens(text):
    return TOKEN.findall(text.casefold())


def main():
    random.seed(SEED); np.random.seed(SEED); torch.manual_seed(SEED)
    torch.set_num_threads(1)
    raw = DATA.read_bytes()
    pairs = [json.loads(x) for x in raw.decode().splitlines() if x.strip()]
    vocab = {"<unk>": 0}
    for pair in pairs:
        for language in ("en", "fr"):
            for token in tokens(pair[language]):
                if token not in vocab: vocab[token] = len(vocab)
    sequences = [torch.tensor([vocab[t] for t in tokens(p[l])], dtype=torch.long) for p in pairs for l in ("en", "fr")]
    batch = nn.utils.rnn.pad_sequence(sequences, batch_first=True, padding_value=0)
    lengths = torch.tensor([len(tokens(p[l])) for p in pairs for l in ("en", "fr")], dtype=torch.float32).unsqueeze(1)
    labels = torch.arange(len(pairs)).repeat_interleave(2)
    class Encoder(nn.Module):
        def __init__(self):
            super().__init__()
            self.embedding = nn.Embedding(len(vocab), 128)
            self.projection = nn.Linear(128, DIM, bias=False)
        def forward(self, ids, lengths):
            mask = (ids != 0).unsqueeze(-1)
            x = (self.embedding(ids) * mask).sum(dim=1) / lengths.clamp_min(1)
            return F.normalize(self.projection(x), p=2, dim=1)
    model = Encoder()
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.025, weight_decay=0.001)
    for epoch in range(500):
        vectors = model(batch, lengths)
        logits = vectors @ vectors.T / 0.08
        logits.fill_diagonal_(-1e9)
        # Each translation pair is positive in both directions; other pairs are negatives.
        targets = torch.arange(len(labels)) ^ 1
        loss = F.cross_entropy(logits, targets)
        optimizer.zero_grad(); loss.backward(); optimizer.step()
    OUT.mkdir(parents=True, exist_ok=True)
    model.eval()
    torch.save({"state_dict": model.state_dict(), "vocab": vocab, "dim": DIM, "seed": SEED}, OUT / "checkpoint.pt")
    manifest = {
        "model": "codex-public-dev-bilingual-mean-embedding",
        "architecture": "token embedding 128d mean pooling -> linear projection 384d -> L2 normalization",
        "training": {"seed": SEED, "framework": f"torch {torch.__version__}", "optimizer": "AdamW", "loss": "symmetric in-batch contrastive cross entropy", "epochs": 500, "pairs": len(pairs), "pair_sha256": hashlib.sha256(raw).hexdigest()},
        "revision": f"dev-enfr-40pairs-seed{SEED}",
        "tokenizer": "Unicode alphanumeric word tokens; casefold; OOV mapped to index 0",
        "vocabulary_sha256": hashlib.sha256(json.dumps(vocab, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        "dimension": DIM, "normalization": "L2", "vocabulary_size": len(vocab),
        "checkpoint_sha256": hashlib.sha256((OUT / "checkpoint.pt").read_bytes()).hexdigest(),
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))

if __name__ == "__main__": main()
