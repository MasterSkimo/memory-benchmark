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
import re
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urlsplit


_ROOT = Path(__file__).resolve().parents[3]
_TOKENIZER_CACHE = _ROOT / ".models/v2/tokenizers"
_TOKENIZER_CACHE_KEY = "9b5ad71b2ce5302211f9c61530b329a4922fc6a4"
_TOKENIZER_SHA256 = "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7"
os.environ.setdefault("TELEMETRY_DISABLED", "1")


def _configure_offline_tiktoken() -> None:
    cache = _TOKENIZER_CACHE / _TOKENIZER_CACHE_KEY
    if not cache.is_file() or hashlib.sha256(cache.read_bytes()).hexdigest() != _TOKENIZER_SHA256:
        raise RuntimeError(
            "Pinned offline cl100k_base asset missing or invalid; run "
            "implementations/v2/cognee/prepare_tokenizer.py"
        )
    # tiktoken officially supports this cache directory and derives the filename
    # from the canonical encoding URL. The asset is hash-checked before Cognee
    # imports its tokenizer, so no network fallback can occur.
    os.environ["TIKTOKEN_CACHE_DIR"] = str(_TOKENIZER_CACHE)


_configure_offline_tiktoken()


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


def _explicit_local_llm_configured(llm_config) -> bool:
    """Require explicit opt-in to a loopback extraction LLM."""
    if os.getenv("COGNEE_LOCAL_INFERENCE_OPT_IN") != "1":
        return False
    if getattr(llm_config, "llm_provider", "").lower() != "ollama":
        return False
    if not _is_loopback_endpoint(getattr(llm_config, "llm_endpoint", "")):
        return False
    # Cognee can route structured extraction through BAML or configured
    # fallbacks, so reject those alternate routes instead of assuming safety.
    if getattr(llm_config, "structured_output_framework", "instructor").lower() != "instructor":
        return False
    if getattr(llm_config, "fallback_endpoint", "") or getattr(llm_config, "baml_llm_endpoint", ""):
        return False
    return True


def _install_common_embedding_engine(counters: dict[str, int]):
    """Adapt the shared V2 neural encoder to Cognee's local vector interface."""
    common_site = _ROOT / "implementations/v2/common-models/.venv/lib/python3.12/site-packages"
    if not common_site.is_dir():
        raise RuntimeError("Shared V2 common-models environment is missing")
    if str(common_site) not in sys.path:
        sys.path.insert(0, str(common_site))
    common_source = _ROOT / "implementations/v2/common-models"
    sys.path.insert(0, str(common_source))
    from embedder import LocalEmbedder

    class CogneeEmbeddingAdapter:
        def __init__(self):
            self.model = LocalEmbedder()
            self.max_completion_tokens = 8191

        async def embed_text(self, text: list[str]) -> list[list[float]]:
            texts = [text] if isinstance(text, str) else text
            counters["embedding_calls"] += 1
            return self.model.encode(texts)

        def get_vector_size(self) -> int:
            return self.model.dimension

        def get_batch_size(self) -> int:
            return 64

        def get_tokenizer(self):
            import tiktoken
            return tiktoken.get_encoding("cl100k_base")

    engine = CogneeEmbeddingAdapter()
    from cognee.infrastructure.databases.vector import create_vector_engine
    from cognee.infrastructure.databases.vector import embeddings

    # Cognee 0.5.1 exposes vector-engine construction as an internal factory.
    # This narrow adapter hook keeps its real LanceDB/Kuzu pipelines while
    # routing all semantic vectors through the benchmark's one shared model.
    create_vector_engine.get_embedding_engine = lambda: engine
    embeddings.get_embedding_engine = lambda: engine
    return engine


class CogneeAdapter:
    def __init__(self, corpus: Path, organization_id: str, knowledge_space_id: str):
        self.corpus = Path(corpus).resolve()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", organization_id):
            raise ValueError("Invalid organization_id path component")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", knowledge_space_id):
            raise ValueError("Invalid knowledge_space_id path component")
        self.organization_id = organization_id
        self.knowledge_space_id = knowledge_space_id
        self.dataset_name = None
        self.ingest_file_reads = 0
        self.ingest_bytes_read = 0
        self.ingest_backend_calls = None
        self.ingest_embedding_calls = None
        self.embedding_calls = 0
        self._embedding_counters = {"embedding_calls": 0}
        self.add_llm_preflight = "NOT_RUN"
        self._sources: dict[str, dict[str, str]] = {}
        self.ingestion_status = "NOT_STARTED"
        self.ingestion_error = None
        self.dataset_id = None

        # Keep Cognee's native local graph/vector and relational stores inside
        # V2 state rather than the V1 candidate or package directory.
        import cognee
        state = Path(__file__).resolve().parent / ".state"
        state.mkdir(parents=True, exist_ok=True)
        cognee.config.system_root_directory(str(state / "system"))
        cognee.config.data_root_directory(str(state / "data"))
        self.embedding_model = _install_common_embedding_engine(self._embedding_counters)

        scope_path = self.corpus / organization_id / knowledge_space_id
        scope = scope_path.resolve()
        if scope != scope_path:
            raise ValueError("Authorized org/project path contains a symlink")
        files = sorted(scope.glob("*.md"))
        if not files:
            raise ValueError("No Markdown sources for the requested authorization scope")
        source_texts = []
        for path in files:
            if path.is_symlink() or path.resolve().parent != scope:
                raise ValueError(f"Markdown source escapes its authorized directory: {path}")
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
            expected_document_id = f"{organization_id}/{knowledge_space_id}/{path.stem}"
            if document_id != expected_document_id:
                raise ValueError(f"Document ID does not match its authorized source path: {path}")
            self._sources[document_id] = {"revision": revision, "text": raw}
            source_texts.append(raw)
        if not source_texts:
            raise ValueError("No authorized Markdown sources after metadata validation")

        # A new source revision set gets a new native Cognee dataset. This keeps
        # stale chunks from an earlier index out of the active retrieval scope.
        revision_fingerprint = "\n".join(
            f"{doc_id}:{source['revision']}:{hashlib.sha256(source['text'].encode()).hexdigest()}"
            for doc_id, source in sorted(self._sources.items())
        )
        self.dataset_name = "bench_" + hashlib.sha256(
            f"{organization_id}/{knowledge_space_id}\n{revision_fingerprint}".encode()
        ).hexdigest()[:24]

        self._cognee = cognee
        # The Cognee dataset is a backend-level namespace; search always passes
        # its resolved ID so the vector engine can constrain retrieval before
        # returning candidates.
        try:
            # Cognee 0.5.1 runs a mandatory LLM connectivity probe even in
            # `add`, although text ingestion itself only resolves and stores
            # source data. When no explicitly approved local LLM is configured,
            # skip that probe for this add call only. Keep the real embedding
            # readiness probe and the real Cognee add pipeline. `cognify` is
            # still gated below and is never replaced by a fake pipeline.
            from cognee.infrastructure.llm.config import get_llm_config
            local_llm_ready = _explicit_local_llm_configured(get_llm_config())
            if local_llm_ready:
                self.add_llm_preflight = "RUN_LOCAL_LLM"
                add_info = _run(cognee.add(source_texts, dataset_name=self.dataset_name))
            else:
                from cognee.infrastructure import llm as llm_api
                from cognee.infrastructure.llm import utils as llm_utils
                original_llm_probe = llm_utils.test_llm_connection

                async def ingestion_only_llm_probe():
                    return None

                llm_api.test_llm_connection = ingestion_only_llm_probe
                llm_utils.test_llm_connection = ingestion_only_llm_probe
                self.add_llm_preflight = "SKIPPED_ADD_ONLY_NO_LOCAL_LLM"
                try:
                    add_info = _run(cognee.add(source_texts, dataset_name=self.dataset_name))
                finally:
                    llm_api.test_llm_connection = original_llm_probe
                    llm_utils.test_llm_connection = original_llm_probe
        except Exception as error:
            self.ingestion_status = "BLOCKED"
            message = str(error)
            if "tiktoken" in message or "openaipublic.blob.core.windows.net" in message:
                response = ("HTTP 403 Forbidden" if "403 Forbidden" in message
                            else "fetch denied by configured proxy")
                self.ingestion_error = (
                    "Cognee add could not fetch its static tiktoken encoding asset from "
                    f"openaipublic.blob.core.windows.net: {response}"
                )
            elif "ProxyError" in message or "Tunnel connection failed" in message:
                self.ingestion_error = (
                    "Cognee add encountered a blocked network dependency through the configured "
                    "proxy; the tokenizer cache was available and no alternate endpoint was used"
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
        self.ingest_embedding_calls = self._embedding_counters["embedding_calls"]
        self.embedding_calls = self._embedding_counters["embedding_calls"]
        self.ingest_backend_calls = 1  # one real Cognee add API call
        self.ingestion_status = "COMPLETED"
        # Never call an external model from this benchmark. Cognee's documented
        # default cognify pipeline invokes its configured LLM for graph
        # extraction and summaries. Only an explicitly local Ollama provider is
        # eligible here; otherwise record the extraction stage as blocked.
        self.extraction_status = "BLOCKED_NO_LOCAL_LLM"
        from cognee.infrastructure.llm.config import get_llm_config
        llm_config = get_llm_config()
        if _explicit_local_llm_configured(llm_config):
            try:
                _run(cognee.cognify(datasets=[self.dataset_id]))
                self.extraction_status = "COMPLETED_LOCAL_OLLAMA_COMMON_EMBEDDINGS"
            except Exception as error:
                self.extraction_status = "BLOCKED_COGNIFY_ERROR"
                self.ingestion_error = f"{type(error).__name__}: {str(error)[:240]}"
            self.embedding_calls = self._embedding_counters["embedding_calls"]
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
        if self.extraction_status == "BLOCKED_COGNIFY_ERROR":
            raise RuntimeError(f"BLOCKED_COGNIFY: {self.ingestion_error}")
        from cognee.modules.search.types import SearchType

        calls_before_search = self._embedding_counters["embedding_calls"]
        result = _run(self._cognee.search(
            str(question["question"]), query_type=SearchType.CHUNKS,
            dataset_ids=[self.dataset_id], top_k=top_k,
        ))
        self.embedding_calls = self._embedding_counters["embedding_calls"]
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
        return {
            "hits": hits,
            "backend_calls": 1,  # one real Cognee search API call
            "file_reads": 0,
            "bytes_read": 0,
            "embedding_calls": self._embedding_counters["embedding_calls"] - calls_before_search,
            "rerank_calls": 0,
            "tool_calls": 0,
        }

    def close(self) -> None:
        # Cognee owns process-global local engines; no per-adapter teardown API.
        return None


def create_adapter(corpus: Path, organization_id: str, knowledge_space_id: str) -> CogneeAdapter:
    return CogneeAdapter(corpus, organization_id, knowledge_space_id)
