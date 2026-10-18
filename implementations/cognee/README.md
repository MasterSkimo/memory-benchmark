# Cognee adapter

Cognee is pinned to **0.5.1**, licensed **Apache-2.0**. Package metadata identifies its source repository as [`topoteretes/cognee`](https://github.com/topoteretes/cognee). This adapter targets Cognee's public `add`, `cognify`, and `search(SearchType.CHUNKS, dataset_ids=...)` APIs. The selected default local storage backends in this release are Kuzu **0.11.3** for graph storage and LanceDB **0.40.0** for vectors.

## Setup and checks

```sh
python3 -m venv implementations/cognee/.venv
implementations/cognee/.venv/bin/python -m pip install -r implementations/cognee/requirements-lock.txt
implementations/cognee/.venv/bin/python -m unittest discover -s implementations/cognee -p 'test_*.py' -v
```

The lock file was captured from the candidate-local Python 3.12.14 environment. The Cognee `add` API also needs its static `tiktoken` encoding asset. In this run, that fetch was denied by the configured proxy with HTTP 403; no auth or raw proxy diagnostics are stored. The `add` return value's `dataset_id` extraction and downstream dataset-scoped operations remain unverified until `add` completes.

## Inference controls

Model-assisted extraction is disabled by default. It can run only when `COGNEE_LOCAL_INFERENCE_OPT_IN=1`, with `LLM_PROVIDER=ollama` and `EMBEDDING_PROVIDER=ollama`, and both `LLM_ENDPOINT` and `EMBEDDING_ENDPOINT` explicitly set to loopback HTTP(S) endpoints. Non-loopback endpoints, BAML/fallback routes, or missing opt-in are rejected. This is a guard on Cognee `cognify`; embedding and graph extraction have not completed in this environment.

## Adapter contract

`create_adapter(corpus, organization_id, knowledge_space_id)` reads only the selected org/project directory, checks frontmatter scope and document ID prefix, then assigns a deterministic Cognee dataset name for that scope. `search(question, top_k=5)` rejects a scope mismatch before backend access and passes the fixed dataset ID to Cognee's CHUNKS vector search. Each hit preserves source `document_id` and `revision`; absent SDK score metadata remains `null`. Backend and embedding call counts are unknown and reported as null.

## Current status

The adapter and scope guards are implemented. The retrieval integration path and real vector retrieval test are blocked before storage by the `tiktoken` asset HTTP 403. Run evidence and corpus-integrity qualification are in `../../results/cognee/README.md` and `../../results/cognee/blocker.md`.
