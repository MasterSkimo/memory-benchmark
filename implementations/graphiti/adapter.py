"""Graphiti Core adapter with deterministic, structured Markdown ingestion.

Graphiti's EpisodicNode storage and Neo4j driver are used directly. LLM-based
episode extraction and embedding are intentionally not invoked in this pilot.
"""
from __future__ import annotations

import asyncio
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

from graphiti_core import Graphiti
from graphiti_core.cross_encoder.client import CrossEncoderClient
from graphiti_core.embedder.client import EmbedderClient
from graphiti_core.llm_client.client import LLMClient
from graphiti_core.nodes import EpisodeType, EpisodicNode
from graphiti_core.utils.maintenance.graph_data_operations import (
    get_fulltext_indices,
    get_range_indices,
)


def _scope_id(org: str, space: str) -> str:
    return hashlib.sha256(f"{org}\0{space}".encode()).hexdigest()


def _markdown_paths(corpus):
    if isinstance(corpus, (str, Path)):
        path = Path(corpus)
        return sorted(path.rglob("*.md")) if path.is_dir() else [path]
    return [Path(p) for p in corpus]


def _metadata(text: str):
    data = {}
    match = re.match(r"\A---\s*\n(.*?)\n---\s*\n?", text, re.S)
    if match:
        for line in match.group(1).splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                data[key.strip()] = value.strip().strip("\"'")
        text = text[match.end():]
    return data, text.strip()


class _NoInferenceLLM(LLMClient):
    async def _generate_response(self, *args, **kwargs):
        raise RuntimeError("LLM extraction is disabled for structured ingestion")


class _NoInferenceEmbedder(EmbedderClient):
    async def create(self, input_data):
        raise RuntimeError("embeddings are disabled for structured ingestion")


class _NoInferenceReranker(CrossEncoderClient):
    async def rank(self, query, passages):
        raise RuntimeError("reranking is disabled for lexical structured retrieval")


class GraphitiAdapter:
    def __init__(self, corpus, organization_id, knowledge_space_id):
        self.organization_id = str(organization_id)
        self.knowledge_space_id = str(knowledge_space_id)
        self.group_id = _scope_id(self.organization_id, self.knowledge_space_id)
        self.ingest_file_reads = 0
        self.ingest_bytes_read = 0
        self.ingest_backend_calls = 0
        self.ingest_embedding_calls = 0
        self._loop = asyncio.new_event_loop()
        self.graph = Graphiti(
            uri="bolt://127.0.0.1:17687", user="neo4j", password="test-password",
            # Structured ingestion/search do not call these clients. Supplying
            # inert placeholders prevents Graphiti's default paid OpenAI
            # clients from being initialized or contacted.
            llm_client=_NoInferenceLLM(None), embedder=_NoInferenceEmbedder(),
            cross_encoder=_NoInferenceReranker(),
        )
        try:
            self._ingest(_markdown_paths(corpus))
        except BaseException:
            self._loop.run_until_complete(self.graph.close())
            self._loop.close()
            raise

    def _ingest(self, paths):
        async def run():
            await self.graph.build_indices_and_constraints()
            # Graphiti Core creates one driver call per generated schema index.
            self.ingest_backend_calls += len(get_range_indices(self.graph.driver.provider))
            self.ingest_backend_calls += len(get_fulltext_indices(self.graph.driver.provider))
            for path in paths:
                raw = path.read_text(encoding="utf-8")
                self.ingest_file_reads += 1
                self.ingest_bytes_read += len(raw.encode("utf-8"))
                meta, body = _metadata(raw)
                org = meta.get("organization_id")
                space = meta.get("knowledge_space_id")
                doc_id = meta.get("document_id")
                revision = meta.get("revision")
                if not org or not space or not doc_id or not revision:
                    raise ValueError(f"{path}: organization_id, knowledge_space_id, document_id, and revision are required")
                if not str(revision).strip():
                    raise ValueError(f"{path}: revision must not be empty")
                if not doc_id.startswith(f"{org}/{space}/"):
                    raise ValueError(f"{path}: document_id prefix does not match its declared organization/project")
                if org != self.organization_id or space != self.knowledge_space_id:
                    continue
                status = meta.get("status", "active").lower()
                node = EpisodicNode(
                    name=f"{doc_id}@{revision}", group_id=self.group_id,
                    source=EpisodeType.text, source_description=f"{doc_id}@{revision}",
                    content=body, valid_at=datetime.now(timezone.utc),
                )
                await node.save(self.graph.driver)
                self.ingest_backend_calls += 1
                await self.graph.driver.execute_query(
                    "MATCH (e:Episodic {uuid: $uuid}) SET e.document_id=$doc, e.revision=$rev, "
                    "e.organization_id=$org, e.knowledge_space_id=$space, e.is_current=$current, "
                    "e.status=$status",
                    uuid=node.uuid, doc=doc_id, rev=revision,
                    org=self.organization_id, space=self.knowledge_space_id,
                    current=status not in {"superseded", "inactive", "archived"}, status=status,
                )
                self.ingest_backend_calls += 1
                if status not in {"superseded", "inactive", "archived"}:
                    await self.graph.driver.execute_query(
                        "MATCH (e:Episodic {group_id:$group, document_id:$doc}) "
                        "WHERE e.uuid <> $uuid SET e.is_current=false",
                        group=self.group_id, doc=doc_id, uuid=node.uuid,
                    )
                    self.ingest_backend_calls += 1
        self._loop.run_until_complete(run())

    def search(self, question: dict, top_k: int = 5) -> dict:
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k <= 0:
            raise ValueError("top_k must be a positive integer")
        org = question.get("organization_id", self.organization_id)
        space = question.get("knowledge_space_id", self.knowledge_space_id)
        if org != self.organization_id or space != self.knowledge_space_id:
            raise PermissionError("question scope does not match authenticated adapter scope")
        query = question.get("question", "")
        terms = set(re.findall(r"[\w-]+", query.casefold()))

        async def run():
            rows, _, _ = await self.graph.driver.execute_query(
                "MATCH (e:Episodic {group_id:$group, organization_id:$org, "
                "knowledge_space_id:$space, is_current:true}) RETURN e.document_id AS document_id, "
                "e.revision AS revision, e.content AS text",
                group=self.group_id, org=self.organization_id, space=self.knowledge_space_id,
            )
            ranked = []
            for row in rows:
                content = row["text"] or ""
                words = set(re.findall(r"[\w-]+", content.casefold()))
                score = len(terms & words) / max(1, len(terms))
                if score:
                    ranked.append((score, row["document_id"], row["revision"], content))
            ranked.sort(key=lambda x: (-x[0], x[1]))
            return [{"document_id": d, "revision": r, "score": s, "text": t}
                    for s, d, r, t in ranked[:top_k]]

        return {"hits": self._loop.run_until_complete(run()), "backend_calls": 1, "file_reads": 0, "bytes_read": 0}

    def close(self):
        self._loop.run_until_complete(self.graph.close())
        self._loop.close()


def create_adapter(corpus, organization_id, knowledge_space_id):
    return GraphitiAdapter(corpus, organization_id, knowledge_space_id)
