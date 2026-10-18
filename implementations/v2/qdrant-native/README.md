# V2 Qdrant native hybrid retriever

Uses the common `LocalEmbedder` in `implementations/v2/common-models/embedder.py`, an embedded Qdrant collection, trained 384D neural dense vectors, hashed sparse lexical vectors, and Qdrant server-side dense+sparse RRF. Trusted organization and project are fixed when the adapter is created. Scope is checked before backend search and again while mapping payloads.

The API is `create_adapter(corpus: Path, organization_id: str, knowledge_space_id: str)`. The returned adapter exposes `search(question: dict, top_k=5)` and returns `hits` with `document_id`, `revision`, `score`, and `text`, plus actual backend/file counters.

Install the exact package pins from `requirements.lock` into one environment. `requirements.txt` also references the shared CPU PyTorch package and Qdrant client. Run tests from the repository root with `PYTHONPATH=implementations/v2/common-models:implementations/v2/qdrant-native python -m pytest -q implementations/v2/qdrant-native/test_adapter.py`.

The shared encoder is a genuinely trained, small neural baseline built because the permitted proxy blocks the official FastEmbed/Hugging Face pretrained distribution. It is not a pretrained sentence model. See `results/v2/models/manifest.json` for the fixed training data hash, seed, exact checkpoint/vocabulary checksums, dimension, normalization, and cross-lingual development smoke check. Its tiny data and word-level OOV handling limit generalization; do not interpret results as representative pretrained-model quality. Test-only toy vectors exercise Qdrant integration and are never used for semantic results.
