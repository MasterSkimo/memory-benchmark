# Qdrant native hybrid Markdown retriever

This adapter indexes Markdown front matter and body into embedded local Qdrant. Each document is stored with its organization, knowledge space, document ID, and source revision. Queries use Qdrant dense and sparse prefetch followed by reciprocal-rank fusion (RRF), with organization and knowledge-space payload filters applied to both prefetches and the fused query.

The dense vector is a deterministic signed hashing vector (384 dimensions); the sparse vector is a deterministic term-frequency vector. These are engineering controls, not neural embeddings, and make no semantic-model claim. No external inference or model weights are used.

Reproduction environment: Python 3.12.14. Install the exact Qdrant Client and transitive package set with `python3 -m pip install -r implementations/qdrant-native/requirements.txt`. Qdrant Client is pinned to 1.15.1 (Apache-2.0). Qdrant runs embedded in process; no Docker or server is required. `create_adapter(corpus, organization_id, knowledge_space_id)` accepts a Markdown directory or paths and binds the adapter to that scope. `search({"question": "..."}, top_k=5)` rejects explicit mismatched organization or project IDs, validates positive integer `top_k`, and returns source IDs, revisions, scores, and text. Ingestion fails closed if `document_id` does not begin with the organization and knowledge-space metadata values.

Run the integration tests with `python -m unittest discover -s implementations/qdrant-native -v`.
