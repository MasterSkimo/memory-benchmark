# Graphiti V2: local semantic temporal graph

This adapter uses Graphiti Core's actual `add_episode` pipeline for entity and
relation extraction and `search_` for native entity/relation retrieval with
BM25 plus dense cosine search. It binds each adapter instance to one trusted
organization and knowledge space before ingestion, supplies a V2-prefixed
Graphiti group ID, filters that group in Graphiti's search API, and checks source
IDs and scope again while mapping source episodes back to citations. Every hit
includes the source revision. Episode text includes the trusted source ID,
revision, scope, and source date so Graphiti can extract relations with temporal
context; source revisions are retained independently so earlier decisions can
still be retrieved.

## Model boundary and current execution status

The shared local neural embedder is available and used directly in process:
`codex-public-dev-bilingual-mean-embedding`, 384 dimensions, L2 normalized,
revision `dev-enfr-40pairs-seed20261018`, checkpoint SHA-256
`db50044db53237fb6f280a7b0c27eb0be45ff18f7108bcd61ea24640cbb15daf`. Its
manifest is at `.models/v2/trained-multilingual/manifest.json`. The adapter
verifies the checkpoint checksum on load and uses it for both Graphiti fact
embeddings and query vectors. A real encoder integrity/dimension/normalization
test runs independently of graph extraction.

No Ollama/llama.cpp runtime, LLM model files, or configured local inference
server were present at implementation time. Therefore **actual entity/relation
extraction and temporal graph retrieval have not yet been run**. The adapter
requires a pinned LLM model ID and explicit loopback OpenAI-compatible endpoint;
it rejects remote endpoints. Graphiti Core does not expose returned token usage,
but the adapter counts actual local LLM and embedding client requests. No model
usage or extraction quality is claimed until the local LLM integration test
passes.

## Configuration

Run Neo4j 5.26.0 on the dedicated V2 port `17687` (or set
`GRAPHITI_NEO4J_URI`), on a V2 group namespace if sharing the server with V1.
Do not clear or delete V1 groups. Provide the local OpenAI-compatible LLM:

```sh
export GRAPHITI_LOCAL_LLM_BASE_URL=http://127.0.0.1:8080/v1
export GRAPHITI_LOCAL_LLM_MODEL='<immutable local model ID>'
```

The shared neural embedder is loaded from `implementations/v2/common-models`
and `.models/v2/trained-multilingual`; it needs no HTTP model server.

Install from the pinned requirements in this directory. Call
`create_adapter(corpus, organization_id, knowledge_space_id)`, then
`adapter.search(question_dict, top_k=5)` and `adapter.close()`.

Run the V2 integration test after mounting `fixtures/v2/vault`, starting a
loopback LLM service, and starting Neo4j with the V2 group namespace:

```sh
PYTHONPATH=implementations/v2/graphiti \
  implementations/v2/graphiti/.venv/bin/python \
  -m unittest implementations/v2/graphiti/test_adapter.py -v
```

Without the local extraction LLM or fixtures, the graph-backed integration test
is skipped with a stage-specific reason. The shared encoder test exercises real
checkpoint loading and inference but does not claim graph extraction evidence.
No V1 source, database group, or result was changed by this implementation.
