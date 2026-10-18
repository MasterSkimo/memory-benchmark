"""Scoped Qdrant hybrid retrieval using shared local neural embeddings."""
from __future__ import annotations

import hashlib
import re
import time
import uuid
from pathlib import Path

from qdrant_client import QdrantClient, models

from embedder import LocalEmbedder

DIM = 384
TOKEN = re.compile(r"[\w-]+", re.UNICODE)
SCOPE_COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
QUESTION_OVERRIDE_KEYS = {"tenant_filter", "tenant_id", "path", "document_id", "revision"}


def _sparse(text: str) -> models.SparseVector:
    counts: dict[int, int] = {}
    for word in TOKEN.findall(text.casefold()):
        idx = int.from_bytes(hashlib.blake2b(word.encode(), digest_size=8).digest(), "little") % 2_000_003
        counts[idx] = counts.get(idx, 0) + 1
    indices = sorted(counts)
    return models.SparseVector(indices=indices, values=[float(counts[i]) for i in indices])


def _parse_markdown(path: Path, raw: str, root: Path, relative_path: Path) -> dict:
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
    parts = relative_path.parts
    if len(parts) < 3 or relative_path.suffix.casefold() != ".md":
        raise ValueError(f"Markdown path must be org/space/document.md under corpus root: {path}")
    expected_org, expected_space = parts[0], parts[1]
    expected_document = relative_path.with_suffix("").as_posix()
    if (fields["organization_id"], fields["knowledge_space_id"], fields["document_id"]) != (expected_org, expected_space, expected_document):
        raise ValueError(f"Front matter scope/document_id does not match corpus-relative path: {path}")
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise ValueError(f"Path escapes corpus root: {path}")
    fields["text"] = body.strip()
    return fields


class QdrantMarkdownAdapter:
    def __init__(self, corpus, organization_id: str, knowledge_space_id: str,
                 *, client: QdrantClient | None = None, collection: str = "markdown_hybrid",
                 embedder=None):
        if (not isinstance(organization_id, str) or not SCOPE_COMPONENT.fullmatch(organization_id)
                or organization_id in {".", ".."}):
            raise ValueError("Trusted organization must be a safe single path component")
        if (not isinstance(knowledge_space_id, str) or not SCOPE_COMPONENT.fullmatch(knowledge_space_id)
                or knowledge_space_id in {".", ".."}):
            raise ValueError("Trusted knowledge space must be a safe single path component")
        self.organization_id = organization_id
        self.knowledge_space_id = knowledge_space_id
        self.client = client or QdrantClient(":memory:")
        self.collection = collection
        self._owned_client = client is None
        self.embedder = embedder if embedder is not None else LocalEmbedder()
        if self.embedder.dimension != DIM:
            raise ValueError(f"Expected {DIM} dimensions, got {self.embedder.dimension}")
        self.ingest_file_reads = self.ingest_bytes_read = self.ingest_backend_calls = 0
        self.ingest_embedding_calls = 0
        self.ingest_embedding_tokens = 0
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
        if not isinstance(corpus, (str, Path)):
            raise TypeError("corpus must be a directory or single path")
        supplied = Path(corpus).absolute()
        if any(component.is_symlink() for component in reversed(supplied.parents)) or supplied.is_symlink():
            raise ValueError(f"Corpus path components may not be symlinks: {supplied}")
        if supplied.is_dir():
            source_root = supplied
            root = supplied.resolve(strict=True)
            paths = sorted(source_root.rglob("*.md"))
        else:
            if supplied.suffix.casefold() != ".md" or len(supplied.parents) < 3:
                raise ValueError("A single Markdown file must be at org/space/document.md")
            source_root = supplied.parents[2]
            root = source_root.resolve(strict=True)
            paths = [supplied]
        items = []
        for path in paths:
            if path.is_symlink():
                raise ValueError(f"Symlink path components are forbidden: {path}")
            relative = path.relative_to(source_root)
            current = source_root
            for component in relative.parts:
                current = current / component
                if current.is_symlink():
                    raise ValueError(f"Symlink path components are forbidden: {current}")
            parts = relative.parts
            if len(parts) < 3 or relative.suffix.casefold() != ".md":
                raise ValueError(f"Markdown path must be org/space/document.md under corpus root: {path}")
            # Reject foreign org/project paths before opening or reading file content.
            if parts[0] != self.organization_id or parts[1] != self.knowledge_space_id:
                continue
            resolved = path.resolve(strict=True)
            if not resolved.is_relative_to(root):
                raise ValueError(f"Path escapes corpus root: {path}")
            raw = resolved.read_bytes()
            self.ingest_file_reads += 1
            self.ingest_bytes_read += len(raw)
            item = _parse_markdown(resolved, raw.decode("utf-8"), root, relative)
            if item.get("status", "").casefold() in {"obsolete", "superseded", "replaced"}:
                continue
            items.append(item)
        if items:
            texts = [item["text"] for item in items]
            dense_vectors = self.embedder.encode(texts)
            self.ingest_embedding_calls += 1
            token_counter = getattr(self.embedder, "token_count", None)
            if callable(token_counter):
                self.ingest_embedding_tokens += sum(token_counter(text) for text in texts)
        else:
            dense_vectors = []
        points = []
        for item, dense in zip(items, dense_vectors, strict=True):
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, item["document_id"]))
            points.append(models.PointStruct(id=point_id, vector={"dense": dense, "sparse": _sparse(item["text"])},
                                             payload=item))
        if points:
            self.client.upsert(self.collection, points=points, wait=True)
            self.ingest_backend_calls += 1
        self.ingest_elapsed_ms += (time.perf_counter() - started) * 1000

    def search(self, question: dict, top_k: int = 5) -> dict:
        if not isinstance(question, dict):
            raise TypeError("question must be an object")
        overrides = QUESTION_OVERRIDE_KEYS.intersection(question)
        if overrides:
            raise PermissionError(f"Question may not override trusted scope or document path: {sorted(overrides)}")
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k <= 0:
            raise ValueError("top_k must be a positive integer")
        # Bind caller authority to immutable adapter scope before any backend call.
        if question.get("organization_id", self.organization_id) != self.organization_id:
            raise PermissionError("Adapter scope mismatch")
        if question.get("knowledge_space_id", self.knowledge_space_id) != self.knowledge_space_id:
            raise PermissionError("Adapter scope mismatch")
        query = question.get("question", question.get("text", ""))
        if not isinstance(query, str) or not query.strip():
            raise ValueError("question text is required")
        dense = self.embedder.encode([query])[0]
        token_counter = getattr(self.embedder, "token_count", None)
        embedding_tokens = token_counter(query) if callable(token_counter) else None
        scope = models.Filter(must=[
            models.FieldCondition(key="organization_id", match=models.MatchValue(value=self.organization_id)),
            models.FieldCondition(key="knowledge_space_id", match=models.MatchValue(value=self.knowledge_space_id)),
        ])
        result = self.client.query_points(
            self.collection,
            prefetch=[
                models.Prefetch(query=dense, using="dense", filter=scope, limit=max(top_k * 4, 20)),
                models.Prefetch(query=_sparse(query), using="sparse", filter=scope, limit=max(top_k * 4, 20)),
            ], query=models.FusionQuery(fusion=models.Fusion.RRF), query_filter=scope,
            limit=top_k, with_payload=True,
        )
        hits = []
        for point in result.points:
            payload = point.payload or {}
            # Enforce authorization again while mapping backend records.
            if payload.get("organization_id") != self.organization_id or payload.get("knowledge_space_id") != self.knowledge_space_id:
                continue
            document_id = payload.get("document_id")
            prefix = f"{self.organization_id}/{self.knowledge_space_id}/"
            if (not isinstance(document_id, str) or not document_id.startswith(prefix)
                    or any(part in {"", ".", ".."} for part in document_id.split("/"))):
                continue
            revision, text = payload.get("revision"), payload.get("text")
            if not isinstance(revision, str) or not isinstance(text, str):
                continue
            hits.append({"document_id": document_id, "revision": revision,
                         "score": point.score, "text": text})
        return {"hits": hits, "backend_calls": 1, "file_reads": 0, "bytes_read": 0,
                "embedding_calls": 1, "embedding_tokens": embedding_tokens}

    def close(self):
        if self._owned_client:
            self.client.close()


def create_adapter(corpus: Path, organization_id: str, knowledge_space_id: str) -> QdrantMarkdownAdapter:
    return QdrantMarkdownAdapter(corpus, organization_id, knowledge_space_id)
