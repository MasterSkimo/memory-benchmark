"""Verified, local-only V2 multilingual contrastive sentence encoder."""
from __future__ import annotations
import hashlib, json, re
from pathlib import Path
from typing import Sequence
import torch
from torch import nn
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[3]
MODEL_DIR = ROOT / ".models/v2/trained-multilingual"
DIMENSION = 384
NORMALIZATION = "l2"
TOKEN = re.compile(r"[^\W_]+", re.UNICODE)


class _Encoder(nn.Module):
    def __init__(self, vocab_size: int):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, 128)
        self.projection = nn.Linear(128, DIMENSION, bias=False)
    def forward(self, ids, lengths):
        mask = (ids != 0).unsqueeze(-1)
        pooled = (self.embedding(ids) * mask).sum(dim=1) / lengths.clamp_min(1)
        return F.normalize(self.projection(pooled), p=2, dim=1)


class LocalEmbedder:
    dimension = DIMENSION
    normalization = NORMALIZATION
    model_name = "codex-public-dev-bilingual-mean-embedding"

    def __init__(self, model_dir: str | Path = MODEL_DIR):
        self.model_dir = Path(model_dir)
        self.manifest = json.loads((self.model_dir / "manifest.json").read_text(encoding="utf-8"))
        checkpoint_path = self.model_dir / "checkpoint.pt"
        actual = hashlib.sha256(checkpoint_path.read_bytes()).hexdigest()
        if actual != self.manifest["checkpoint_sha256"]:
            raise ValueError("Neural encoder checkpoint checksum mismatch")
        self.model_revision = actual
        self.vocab = self._load_vocab(checkpoint_path)
        self.model = _Encoder(len(self.vocab))
        payload = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
        self.model.load_state_dict(payload["state_dict"])
        self.model.eval()

    @staticmethod
    def _load_vocab(checkpoint_path):
        return torch.load(checkpoint_path, map_location="cpu", weights_only=True)["vocab"]

    def token_count(self, text: str) -> int:
        """Count the encoder input tokens before vocabulary lookup/OOV masking."""
        return len(TOKEN.findall(text.casefold()))

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        if not all(isinstance(text, str) for text in texts):
            raise TypeError("texts must contain only strings")
        if not texts:
            return []
        seqs = [[self.vocab.get(t, 0) for t in TOKEN.findall(text.casefold())] for text in texts]
        lengths = torch.tensor([max(1, len(s)) for s in seqs], dtype=torch.float32).unsqueeze(1)
        width = max(int(x) for x in lengths.squeeze(1))
        ids = torch.zeros((len(seqs), width), dtype=torch.long)
        for i, seq in enumerate(seqs):
            if seq:
                ids[i, :len(seq)] = torch.tensor(seq, dtype=torch.long)
        with torch.inference_mode():
            vectors = self.model(ids, lengths)
        return vectors.tolist()
