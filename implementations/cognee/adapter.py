"""Cognee-backed, dataset-scoped Markdown retriever.

Uses Cognee's public add -> cognify -> CHUNKS search flow. Cognee's default
cognify pipeline performs model-assisted graph extraction and summarization;
that stage needs a configured model and is never silently replaced here.
"""
from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


def _run(awaitable):
    """Run an async Cognee API from this synchronous benchmark interface."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    raise RuntimeError("Cognee adapter requires a synchronous caller (no running event loop)")


def _metadata(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    if text.startswith("---"):
        for line in text.splitlines()[1:]:
            if line.strip() == "---":
                break
            if ":" in line:
                key, value = line.split(":", 1)
                fields[key.strip()] = value.strip()
    return fields


def _is_loopback_endpoint(endpoint: str | None) -> bool:
    if not endpoint:
        return False
    parsed = urlsplit(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
        return False
    try:
        return ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        return parsed.hostname.lower() == "localhost"


def _explicit_local_inference_configured(llm_config, embedding_config) -> bool:
    """Require an explicit opt-in and local endpoints for both model stages."""
    if os.getenv("COGNEE_LOCAL_INFERENCE_OPT_IN") != "1":
        return False
    if getattr(llm_config, "llm_provider", "").lower() != "ollama":
        return False
    if getattr(embedding_config, "embedding_provider", "").lower() != "ollama":
        return False
    if not _is_loopback_endpoint(getattr(llm_config, "llm_endpoint", "")):
        return False
    if not _is_loopback_endpoint(getattr(embedding_config, "embedding_endpoint", "")):
        return False
    # Cognee can route structured extraction through BAML or configured
    # fallbacks, so reject those alternate routes instead of assuming safety.
    if getattr(llm_config, "structured_output_framework", "instructor").lower() != "instructor":
        return False
    if getattr(llm_config, "fallback_endpoint", "") or getattr(llm_config, "baml_llm_endpoint", ""):
        return False
    return True


class CogneeAdapter:
    def __init__(self, corpus: Path, organization_id: str, knowledge_space_id: str):
        self.corpus = Path(corpus).resolve()
        self.organization_id = organization_id
        self.knowledge_space_id = knowledge_space_id
        self.dataset_name = "bench_" + hashlib.sha256(
            f"{organization_id}/{knowledge_space_id}".encode()
        ).hexdigest()[:24]
        self.ingest_file_reads = 0
        self.ingest_bytes_read = 0
        self.ingest_backend_calls = None
        self.ingest_embedding_calls = None
        self._sources: dict[str, dict[str, str]] = {}
        self.ingestion_status = "NOT_STARTED"
        self.ingestion_error = None
        self.dataset_id = None

        # Keep Cognee's native local graph/vector and relational stores inside
        # this candidate folder rather than its installed package directory.
        import cognee
        state = Path(__file__).resolve().parent / ".state"
        state.mkdir(parents=True, exist_ok=True)
        cognee.config.system_root_directory(str(state / "system"))
        cognee.config.data_root_directory(str(state / "data"))

        files = sorted(self.corpus.glob(f"{organization_id}/{knowledge_space_id}/*.md"))
        if not files:
            raise ValueError("No Markdown sources for the requested authorization scope")
        source_texts = []
        for path in files:
            raw = path.read_text(encoding="utf-8")
            self.ingest_file_reads += 1
            self.ingest_bytes_read += len(raw.encode("utf-8"))
            meta = _metadata(raw)
            if (meta.get("organization_id") != organization_id or
                    meta.get("knowledge_space_id") != knowledge_space_id):
                raise ValueError(f"Markdown scope metadata does not match its authorized path: {path}")
            document_id = meta.get("document_id")
            revision = meta.get("revision")
            if not document_id or not revision:
                raise ValueError(f"Missing document_id or revision in {path}")
            if not document_id.startswith(f"{organization_id}/{knowledge_space_id}/"):
                raise ValueError(f"Document ID is outside its authorized org/project scope: {path}")
            self._sources[document_id] = {"revision": revision, "text": raw}
            source_texts.append(raw)
        if not source_texts:
            raise ValueError("No authorized Markdown sources after metadata validation")

        self._cognee = cognee
        # The Cognee dataset is a backend-level namespace; search always passes
        # its resolved ID so the vector engine can constrain retrieval before
        # returning candidates.
        try:
            add_info = _run(cognee.add(source_texts, dataset_name=self.dataset_name))
        except Exception as error:
            self.ingestion_status = "BLOCKED"
            message = str(error)
            if "tiktoken" in message or "openaipublic.blob.core.windows.net" in message or "ProxyError" in message:
                response = ("HTTP 403 Forbidden" if "403 Forbidden" in message
                            else "fetch denied by configured proxy")
                self.ingestion_error = (
                    "Cognee add could not fetch its static tiktoken encoding asset from "
                    f"openaipublic.blob.core.windows.net: {response}"
                )
            else:
                self.ingestion_error = f"{type(error).__name__}: {message[:220]}"
            self.extraction_status = "NOT_REACHED"
            self._cognee = cognee
            return
        self.dataset_id = getattr(add_info, "dataset_id", None)
        if self.dataset_id is None and isinstance(add_info, dict):
            self.dataset_id = add_info.get("dataset_id")
        if self.dataset_id is None:
            raise RuntimeError("Cognee add did not return a dataset_id")
        self.ingestion_status = "COMPLETED"
        # Never call an external model from this benchmark. Cognee's documented
        # default cognify pipeline invokes its configured LLM for graph
        # extraction and summaries. Only an explicitly local Ollama provider is
        # eligible here; otherwise record the extraction stage as blocked.
        self.extraction_status = "BLOCKED_NO_LOCAL_LLM"
        from cognee.infrastructure.llm.config import get_llm_config
        from cognee.infrastructure.databases.vector.embeddings.config import get_embedding_config
        llm_config = get_llm_config()
        embedding_config = get_embedding_config()
        if _explicit_local_inference_configured(llm_config, embedding_config):
            _run(cognee.cognify(datasets=[self.dataset_id]))
            self.extraction_status = "COMPLETED_LOCAL_OLLAMA"
        elif (os.getenv("COGNEE_LOCAL_INFERENCE_OPT_IN") == "1" or
              os.getenv("LLM_PROVIDER", "").lower() == "ollama" or
              os.getenv("EMBEDDING_PROVIDER", "").lower() == "ollama"):
            self.extraction_status = "BLOCKED_UNVERIFIED_LOCAL_ENDPOINTS"

    def search(self, question: dict, top_k: int = 5) -> dict:
        if question.get("organization_id") != self.organization_id or question.get("knowledge_space_id") != self.knowledge_space_id:
            raise PermissionError("Question authorization scope does not match this adapter")
        if not 1 <= top_k <= 5:
            raise ValueError("Pilot adapter permits top_k from 1 through 5")
        if self.ingestion_status != "COMPLETED":
            raise RuntimeError(f"BLOCKED_INGESTION: {self.ingestion_error or 'Cognee add failed'}")
        if self.extraction_status == "BLOCKED_NO_LOCAL_LLM":
            raise RuntimeError(
                "BLOCKED_EXTRACTION: Cognee graph/vector indexing requires cognify; "
                "local inference requires COGNEE_LOCAL_INFERENCE_OPT_IN=1 and verified "
                "loopback Ollama LLM and embedding endpoints"
            )
        if self.extraction_status == "BLOCKED_UNVERIFIED_LOCAL_ENDPOINTS":
            raise RuntimeError(
                "BLOCKED_EXTRACTION: local inference opt-in/provider configuration did not "
                "verify both Ollama endpoints as loopback"
            )
        from cognee.modules.search.types import SearchType

        result = _run(self._cognee.search(
            str(question["question"]), query_type=SearchType.CHUNKS,
            dataset_ids=[self.dataset_id], top_k=top_k,
        ))
        records = result if isinstance(result, list) else [result]
        hits: list[dict[str, Any]] = []
        for record in records:
            payloads = getattr(record, "search_result", record)
            if isinstance(payloads, dict):
                payloads = [payloads]
            if not isinstance(payloads, list):
                continue
            for payload in payloads:
                if not isinstance(payload, dict):
                    continue
                text = str(payload.get("text", payload.get("chunk", "")))
                meta = _metadata(text)
                doc_id = meta.get("document_id")
                if not doc_id or doc_id not in self._sources:
                    continue
                # This guard also rejects malformed or cross-scope provenance;
                # the Cognee dataset constraint already applied during search.
                if not doc_id.startswith(f"{self.organization_id}/{self.knowledge_space_id}/"):
                    continue
                source = self._sources[doc_id]
                if meta.get("revision") != source["revision"]:
                    continue
                score = payload.get("score", payload.get("similarity"))
                hits.append({"document_id": doc_id, "revision": source["revision"],
                             "score": float(score) if score is not None else None,
                             "text": text})
                if len(hits) == top_k:
                    break
            if len(hits) == top_k:
                break
        return {"hits": hits, "backend_calls": None, "file_reads": None,
                "bytes_read": None, "embedding_calls": None, "rerank_calls": None,
                "tool_calls": None}

    def close(self) -> None:
        # Cognee owns process-global local engines; no per-adapter teardown API.
        return None


def create_adapter(corpus: Path, organization_id: str, knowledge_space_id: str) -> CogneeAdapter:
    return CogneeAdapter(corpus, organization_id, knowledge_space_id)
