"""Qdrant-backed hybrid Markdown retrieval; dense vectors are deterministic hashing controls."""
from __future__ import annotations

import hashlib
import re
import time
import uuid
from pathlib import Path

from qdrant_client import QdrantClient, models

DIM = 384
TOKEN = re.compile(r"[\w-]+", re.UNICODE)


def _tokens(text: str) -> list[str]:
    return [w.casefold() for w in TOKEN.findall(text)]


def _vectors(text: str) -> tuple[list[float], models.SparseVector]:
    dense = [0.0] * DIM
    counts: dict[int, int] = {}
    for word in _tokens(text):
        digest = hashlib.blake2b(word.encode(), digest_size=8).digest()
        n = int.from_bytes(digest, "little")
        idx = n % DIM
        dense[idx] += 1.0 if (n >> 8) & 1 else -1.0
        term = n % 2_000_003
        counts[term] = counts.get(term, 0) + 1
    norm = sum(x * x for x in dense) ** 0.5 or 1.0
    dense = [x / norm for x in dense]
    indices = sorted(counts)
    return dense, models.SparseVector(indices=indices, values=[float(counts[i]) for i in indices])


def _parse_markdown(path: Path, raw: str | None = None) -> dict:
    raw = raw if raw is not None else path.read_text(encoding="utf-8")
    if not raw.startswith("---\n"):
        raise ValueError(f"Missing YAML front matter: {path}")
    header, sep, body = raw[4:].partition("\n---\n")
    if not sep:
        raise ValueError(f"Malformed YAML front matter: {path}")
    fields = {}
    for line in header.splitlines():
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip()] = value.strip().strip("\"'")
    for key in ("document_id", "organization_id", "knowledge_space_id", "revision"):
        if not fields.get(key):
            raise ValueError(f"Missing {key}: {path}")
    expected_prefix = f"{fields['organization_id']}/{fields['knowledge_space_id']}/"
    if not fields["document_id"].startswith(expected_prefix):
        raise ValueError(f"document_id must begin with {expected_prefix!r}: {path}")
    fields["text"] = body.strip()
    fields["source_path"] = str(path)
    return fields


class QdrantMarkdownAdapter:
    def __init__(self, corpus, organization_id: str, knowledge_space_id: str,
                 *, client: QdrantClient | None = None, collection: str = "markdown_hybrid"):
        self.organization_id = organization_id
        self.knowledge_space_id = knowledge_space_id
        self.client = client or QdrantClient(":memory:")
        self.collection = collection
        self._owned_client = client is None
        self.ingest_file_reads = 0
        self.ingest_bytes_read = 0
        self.ingest_backend_calls = 0
        self.ingest_embedding_calls = 0
        self.ingest_elapsed_ms = 0.0
        self._ensure_collection()
        self.ingest(corpus)

    def _ensure_collection(self):
        if self.client.collection_exists(self.collection):
            self.client.delete_collection(self.collection)
        self.client.create_collection(
            self.collection,
            vectors_config={"dense": models.VectorParams(size=DIM, distance=models.Distance.COSINE)},
            sparse_vectors_config={"sparse": models.SparseVectorParams(index=models.SparseIndexParams(on_disk=False))},
        )
        for field in ("organization_id", "knowledge_space_id", "document_id"):
            self.client.create_payload_index(self.collection, field, models.PayloadSchemaType.KEYWORD)

    def ingest(self, corpus):
        started = time.perf_counter()
        paths = [Path(corpus)] if isinstance(corpus, (str, Path)) else [Path(p) for p in corpus]
        if len(paths) == 1 and paths[0].is_dir():
            paths = sorted(paths[0].rglob("*.md"))
        points = []
        for path in paths:
            raw = Path(path).read_bytes()
            self.ingest_file_reads += 1
            self.ingest_bytes_read += len(raw)
            item = _parse_markdown(Path(path), raw.decode("utf-8"))
            dense, sparse = _vectors(item["text"])
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, item["document_id"]))
            points.append(models.PointStruct(id=point_id, vector={"dense": dense, "sparse": sparse}, payload=item))
        if points:
            self.client.upsert(self.collection, points=points, wait=True)
            self.ingest_backend_calls += 1
        self.ingest_elapsed_ms += (time.perf_counter() - started) * 1000

    def search(self, question: dict, top_k: int = 5) -> dict:
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k <= 0:
            raise ValueError("top_k must be a positive integer")
        org = question.get("organization_id", self.organization_id)
        space = question.get("knowledge_space_id", self.knowledge_space_id)
        if org != self.organization_id or space != self.knowledge_space_id:
            raise PermissionError("Adapter scope mismatch")
        query = question.get("question", question.get("text", ""))
        dense, sparse = _vectors(query)
        scope = models.Filter(must=[
            models.FieldCondition(key="organization_id", match=models.MatchValue(value=self.organization_id)),
            models.FieldCondition(key="knowledge_space_id", match=models.MatchValue(value=self.knowledge_space_id)),
        ])
        # Both prefetches are server-side filtered before RRF combines candidates.
        result = self.client.query_points(
            self.collection,
            prefetch=[
                models.Prefetch(query=dense, using="dense", filter=scope, limit=max(top_k * 4, 20)),
                models.Prefetch(query=sparse, using="sparse", filter=scope, limit=max(top_k * 4, 20)),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF), query_filter=scope,
            limit=top_k, with_payload=True,
        )
        hits = [{"document_id": p.payload["document_id"], "revision": p.payload["revision"],
                 "score": p.score, "text": p.payload["text"]} for p in result.points]
        return {"hits": hits, "backend_calls": None, "file_reads": 0, "bytes_read": 0}

    def close(self):
        if self._owned_client:
            self.client.close()


def create_adapter(corpus, organization_id: str, knowledge_space_id: str) -> QdrantMarkdownAdapter:
    return QdrantMarkdownAdapter(corpus, organization_id, knowledge_space_id)
