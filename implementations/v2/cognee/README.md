# Cognee V2 adapter

This candidate uses Cognee **0.5.1** (Apache-2.0), Kuzu **0.11.3** for graph storage, and LanceDB **0.40.0** for vectors. The adapter uses Cognee's real `add`, `cognify(datasets=[dataset_id])`, and dataset-scoped `search(SearchType.CHUNKS, dataset_ids=[dataset_id])` APIs. State stays under `implementations/v2/cognee/.state/`.

## Offline tokenizer

Cognee 0.5.1 asks `tiktoken` for the `cl100k_base` ranks during ingestion. `gpt-tokenizer` **4.1.0** (MIT; npm package from [`niieani/gpt-tokenizer`](https://github.com/niieani/gpt-tokenizer), npm tarball `https://registry.npmjs.org/gpt-tokenizer/-/gpt-tokenizer-4.1.0.tgz`) packages that encoding's rank table. Its npm SRI is `sha512-r7Op7S3iPy9vGpcfHmfIlLN/+/mNL2kXDy3N/ppp2xC2pm57pyYTt3fqsncMZ/yfIT+d3mTGhd7H6fcF/qiqWg==`; tarball SHA-256 is `ec0f7e3eea8e4f56b30297af68e4a52629707bdc59530f4a82d81ac03aad4447`. The package and OpenAI `tiktoken` encoding declare MIT licensing. The derived ranks match the canonical cl100k asset checksum exactly: `223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7`.

The ignored package archive is `.models/v2/cognee/gpt-tokenizer-4.1.0.tgz`. To create it from the official npm package if it is not already provisioned, run `npm pack gpt-tokenizer@4.1.0 --pack-destination .models/v2/cognee` and verify the tarball checksum above. Then run:

```sh
python3 implementations/v2/cognee/prepare_tokenizer.py
```

The script converts the bundled rank table into `tiktoken` cache format, verifies the canonical SHA-256, and writes the supported cache key under ignored `.models/v2/tokenizers/`. The adapter verifies both the canonical URL cache key and content checksum, sets `TIKTOKEN_CACHE_DIR` before importing Cognee, and therefore does not request the blocked Azure blob URL. The asset was verified with `tiktoken.get_encoding("cl100k_base")` while network access was unavailable.

## Local model wiring and current stage boundary

Cognee's embedding factory is adapted to the shared V2 `LocalEmbedder` (`.models/v2/trained-multilingual/checkpoint.pt`, 384 dimensions, L2 normalized, checkpoint SHA-256 `db50044db53237fb6f280a7b0c27eb0be45ff18f7108bcd61ea24640cbb15daf`). Cognee continues to run its own local database and vector operations. There is no embedding endpoint or remote fallback. The common model has the limitations in `../../../results/v2/models/manifest.json`: it was contrastively trained on 40 authored EN/FR development pairs and is not a pretrained general-purpose encoder.

The verified real `add` path completed, returned a Cognee dataset ID, persisted the source under V2 state, and ran Cognee's embedding readiness probe through the shared local encoder. Cognee 0.5.1 unnecessarily requires an LLM connectivity probe even for its add-only source storage stage; in the no-local-LLM configuration, the adapter skips only that probe for `add`, then calls the actual SDK add pipeline and keeps telemetry disabled through Cognee's supported `TELEMETRY_DISABLED=1` option. This does not synthesize chunks, graph nodes, or vectors. Dataset names include a fingerprint of all exact document revisions and content hashes, so revision changes create a fresh backend dataset.

No local extraction LLM or runtime is available in this environment. The adapter calls real `cognify` only when `COGNEE_LOCAL_INFERENCE_OPT_IN=1`, Cognee's configured provider is Ollama, and the LLM endpoint is loopback. It is currently marked `BLOCKED_NO_LOCAL_LLM`; graph extraction, chunk/vector indexing, and CHUNKS retrieval have not run. Consequently, no Cognee retrieval score or chunk provenance mapping is claimed. The 40-question evaluator must leave this candidate unscored until a local extraction LLM is provisioned.

## Setup and integration check

```sh
python3 -m venv implementations/v2/cognee/.venv
implementations/v2/cognee/.venv/bin/python -m pip install -r implementations/v2/cognee/requirements-lock.txt
TELEMETRY_DISABLED=1 implementations/v2/cognee/.venv/bin/python -m unittest discover -s implementations/v2/cognee -p 'test_*.py' -v
```

Tests run real Cognee add operations, verify returned dataset IDs and revision-specific datasets, exercise the shared neural embedding integration, and reject forged scope/document metadata, unsafe path components, and symlink sources before ingestion. Search tests intentionally assert the exact extraction blocker rather than treating it as a successful retrieval.
