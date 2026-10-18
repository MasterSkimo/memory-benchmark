"""Graphiti Core adapter using its native extraction and graph search pipeline.

Both model clients are restricted to explicitly configured loopback endpoints.
No structured-only episode shortcut or custom lexical retrieval is used.
"""
from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import importlib.util
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from graphiti_core import Graphiti
from graphiti_core.cross_encoder.client import CrossEncoderClient
from graphiti_core.embedder.client import EmbedderClient, EmbedderConfig
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.search.search_config import (
    EdgeReranker, EdgeSearchConfig, EdgeSearchMethod, NodeReranker,
    NodeSearchConfig, NodeSearchMethod, SearchConfig,
)
from graphiti_core.search.search_filters import ComparisonOperator, DateFilter, SearchFilters


def _scope_id(org: str, space: str) -> str:
    return "v2-" + hashlib.sha256(f"{org}\0{space}".encode()).hexdigest()


def _local_url(name: str, default: str) -> str:
    url = os.getenv(name, default)
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"{name} must be an HTTP(S) loopback endpoint")
    try:
        is_loopback = ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        is_loopback = parsed.hostname.lower() == "localhost"
    if not is_loopback:
        raise ValueError(f"{name} must point to loopback; external inference is prohibited")
    return url


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


class _CountingLocalLLM(OpenAIGenericClient):
    def __init__(self, config):
        super().__init__(config)
        self.request_count = 0

    async def _generate_response(self, *args, **kwargs):
        self.request_count += 1
        return await super()._generate_response(*args, **kwargs)


class _CountingLocalEmbedder(EmbedderClient):
    """Graphiti embedder backed by the shared V2 neural checkpoint in process."""
    def __init__(self, model):
        self.model = model
        self.config = EmbedderConfig(embedding_dim=model.dimension)
        self.request_count = 0
        self.vector_count = 0

    async def create(self, input_data):
        self.request_count += 1
        self.vector_count += 1
        text = input_data if isinstance(input_data, str) else " ".join(str(x) for x in input_data)
        return self.model.encode([text])[0]

    async def create_batch(self, input_data_list):
        self.request_count += 1
        self.vector_count += len(input_data_list)
        return self.model.encode(input_data_list)


def _shared_local_embedder():
    module_path = Path(__file__).parents[1] / "common-models" / "embedder.py"
    spec = importlib.util.spec_from_file_location("v2_shared_local_embedder", module_path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot load shared V2 embedder from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.LocalEmbedder()


class _NoRemoteReranker(CrossEncoderClient):
    async def rank(self, query, passages):
        raise RuntimeError("Reranking is disabled; native graph search uses reciprocal-rank fusion")


class GraphitiAdapter:
    def __init__(self, corpus, organization_id, knowledge_space_id):
        self.organization_id = str(organization_id)
        self.knowledge_space_id = str(knowledge_space_id)
        self.group_id = _scope_id(self.organization_id, self.knowledge_space_id)
        self.ingest_file_reads = self.ingest_bytes_read = 0
        self.ingest_backend_calls = self.episodes_ingested = 0
        self._backend_calls_total = 0
        self.ingest_seconds = 0.0
        self._loop = asyncio.new_event_loop()

        llm_url = _local_url("GRAPHITI_LOCAL_LLM_BASE_URL", "http://127.0.0.1:8080/v1")
        llm_model = os.getenv("GRAPHITI_LOCAL_LLM_MODEL", "")
        if not llm_model:
            raise RuntimeError("Set pinned local GRAPHITI_LOCAL_LLM_MODEL before ingestion")

        self.local_llm = _CountingLocalLLM(LLMConfig(
            api_key="local-only", base_url=llm_url, model=llm_model,
            small_model=llm_model, temperature=0, max_tokens=2048))
        self.shared_embedder_model = _shared_local_embedder()
        self.local_embedder = _CountingLocalEmbedder(self.shared_embedder_model)
        self.graph = Graphiti(
            uri=os.getenv("GRAPHITI_NEO4J_URI", "bolt://127.0.0.1:17687"),
            user=os.getenv("GRAPHITI_NEO4J_USER", "neo4j"),
            password=os.getenv("GRAPHITI_NEO4J_PASSWORD", "test-password"),
            llm_client=self.local_llm,
            embedder=self.local_embedder,
            cross_encoder=_NoRemoteReranker(),
        )
        driver_execute_query = self.graph.driver.execute_query

        async def count_driver_call(*args, **kwargs):
            self._backend_calls_total += 1
            return await driver_execute_query(*args, **kwargs)

        self.graph.driver.execute_query = count_driver_call
        try:
            self._ingest(_markdown_paths(corpus))
        except BaseException:
            self._loop.run_until_complete(self.graph.close())
            self._loop.close()
            raise

    def _ingest(self, paths):
        async def run():
            started = time.perf_counter()
            backend_before = self._backend_calls_total
            await self.graph.build_indices_and_constraints()
            for path in paths:
                raw = path.read_text(encoding="utf-8")
                self.ingest_file_reads += 1
                self.ingest_bytes_read += len(raw.encode("utf-8"))
                meta, body = _metadata(raw)
                org, space = meta.get("organization_id"), meta.get("knowledge_space_id")
                doc_id, revision = meta.get("document_id"), meta.get("revision")
                if not org or not space or not doc_id or not revision:
                    raise ValueError(f"{path}: organization_id, knowledge_space_id, document_id, revision are required")
                if not doc_id.startswith(f"{org}/{space}/"):
                    raise ValueError(f"{path}: document_id prefix does not match declared organization/project")
                if org != self.organization_id or space != self.knowledge_space_id:
                    continue
                reference = (meta.get("updated_at") or meta.get("date") or
                             meta.get("valid_at") or meta.get("valid_from"))
                try:
                    reference_time = datetime.fromisoformat(reference.replace("Z", "+00:00")) if reference else datetime.now(timezone.utc)
                except (ValueError, AttributeError):
                    reference_time = datetime.now(timezone.utc)
                if reference_time.tzinfo is None:
                    reference_time = reference_time.replace(tzinfo=timezone.utc)
                context = (f"Source document: {doc_id}\nRevision: {revision}\n"
                           f"Organization: {org}\nKnowledge space: {space}\n"
                           f"Source date: {reference_time.isoformat()}\n\n{body}")
                await self.graph.add_episode(
                    name=f"{doc_id}@{revision}", episode_body=context,
                    source_description=f"Markdown note {doc_id}@{revision}",
                    reference_time=reference_time, group_id=self.group_id,
                )
                self.episodes_ingested += 1
            self.ingest_seconds = time.perf_counter() - started
            self.ingest_backend_calls = self._backend_calls_total - backend_before
        self._loop.run_until_complete(run())

    def search(self, question: dict, top_k: int = 5) -> dict:
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k <= 0:
            raise ValueError("top_k must be a positive integer")
        org = question.get("organization_id", self.organization_id)
        space = question.get("knowledge_space_id", self.knowledge_space_id)
        if org != self.organization_id or space != self.knowledge_space_id:
            raise PermissionError("question scope does not match authenticated adapter scope")
        query = str(question.get("question", ""))
        config = SearchConfig(
            edge_config=EdgeSearchConfig(
                search_methods=[EdgeSearchMethod.cosine_similarity, EdgeSearchMethod.bm25],
                reranker=EdgeReranker.rrf),
            node_config=NodeSearchConfig(
                search_methods=[NodeSearchMethod.cosine_similarity, NodeSearchMethod.bm25],
                reranker=NodeReranker.rrf),
            limit=top_k,
        )
        search_filter = None
        as_of = question.get("as_of")
        if as_of:
            as_of_time = datetime.fromisoformat(str(as_of).replace("Z", "+00:00"))
            if as_of_time.tzinfo is None:
                as_of_time = as_of_time.replace(tzinfo=timezone.utc)
            search_filter = SearchFilters(valid_at=[[
                DateFilter(date=as_of_time, comparison_operator=ComparisonOperator.less_than_equal)
            ]])

        async def run():
            before = time.perf_counter()
            backend_before = self._backend_calls_total
            results = await self.graph.search_(query, config=config, group_ids=[self.group_id],
                                               search_filter=search_filter)
            # Graphiti's native vector/BM25 entity and relation searches select
            # episode UUIDs. This parameterized graph lookup only resolves trusted
            # citations and scope metadata after native ranking.
            episode_ids = set()
            for edge in results.edges:
                episode_ids.update(edge.episodes)
            if not episode_ids:
                return [], len(results.edges), self._backend_calls_total - backend_before, (time.perf_counter() - before)
            rows, _, _ = await self.graph.driver.execute_query(
                "MATCH (ep:Episodic) WHERE ep.uuid IN $uuids AND ep.group_id=$group "
                "RETURN ep.uuid AS uuid, ep.content AS text",
                uuids=list(episode_ids), group=self.group_id)
            content_by_uuid = {row["uuid"]: row["text"] or "" for row in rows}
            hits, seen = [], set()
            for row in rows:
                content = content_by_uuid.get(row["uuid"], "")
                if not content:
                    continue
                doc = re.search(r"(?m)^Source document: (.+)$", content)
                rev = re.search(r"(?m)^Revision: (.+)$", content)
                if not doc or not rev:
                    continue
                doc_id, revision = doc.group(1), rev.group(1)
                if not doc_id.startswith(f"{self.organization_id}/{self.knowledge_space_id}/"):
                    continue
                key = (doc_id, revision)
                if key in seen:
                    continue
                seen.add(key)
                body = content.split("\n\n", 1)[-1]
                hits.append({"document_id": doc_id, "revision": revision,
                             "score": 1.0 / len(hits + [None]), "text": body})
            # Keep citation order from Graphiti's native ranked edge results. The
            # SDK omits numeric relevance scores from SearchResults, so score is a
            # transparent reciprocal rank, not a model confidence estimate.
            hits_by_key = {(h["document_id"], h["revision"]): h for h in hits}
            ranked_hits, seen = [], set()
            for edge in results.edges:
                for episode_uuid in edge.episodes:
                    content = content_by_uuid.get(episode_uuid, "")
                    doc = re.search(r"(?m)^Source document: (.+)$", content)
                    rev = re.search(r"(?m)^Revision: (.+)$", content)
                    if not doc or not rev:
                        continue
                    key = (doc.group(1), rev.group(1))
                    if key in hits_by_key and key not in seen:
                        seen.add(key)
                        ranked_hits.append(hits_by_key[key])
                        if len(ranked_hits) >= top_k:
                            break
                if len(ranked_hits) >= top_k:
                    break
            for rank, hit in enumerate(ranked_hits, start=1):
                hit["score"] = 1.0 / rank
            hits = ranked_hits
            return hits, len(results.edges), self._backend_calls_total - backend_before, (time.perf_counter() - before)

        llm_before = self.local_llm.request_count
        embed_before = self.local_embedder.request_count
        vectors_before = self.local_embedder.vector_count
        hits, graph_facts, backend_calls, elapsed = self._loop.run_until_complete(run())
        return {"hits": hits, "backend_calls": backend_calls, "file_reads": 0, "bytes_read": 0,
                "embedding_calls": self.local_embedder.request_count - embed_before,
                "embedding_vectors": self.local_embedder.vector_count - vectors_before,
                "llm_calls": self.local_llm.request_count - llm_before,
                "graph_facts": graph_facts, "elapsed_seconds": elapsed}

    def close(self):
        self._loop.run_until_complete(self.graph.close())
        self._loop.close()


def create_adapter(corpus, organization_id, knowledge_space_id):
    return GraphitiAdapter(corpus, organization_id, knowledge_space_id)
