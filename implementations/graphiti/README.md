# Graphiti temporal graph pilot

This adapter writes Markdown as Graphiti Core `EpisodicNode` records into Neo4j 5.26.0 Community Edition and uses Graphiti Core's Neo4j driver for scoped retrieval. It uses an explicitly structured, non-LLM ingestion path: source front matter and body are retained as episode metadata/content, and lexical overlap ranks retrieved episodes. Graphiti extraction, embeddings, reranking, and answer generation are disabled; this is not the LLM-extracted Graphiti pipeline.

The scope is bound in `create_adapter(corpus, organization_id, knowledge_space_id)`. Input metadata must include non-empty organization, project, document ID, and revision, and the document ID's `org/project/` prefix must match the metadata before any graph write. Both matching corpus metadata and the Neo4j query must match the bound organization and project. Superseded, inactive, and archived notes are excluded; a newly ingested active revision marks earlier revisions of that document as superseded in the graph. Returned hits include the stored document ID and revision. `top_k` must be a positive integer.

## Setup

```sh
python3 -m venv implementations/graphiti/.venv
implementations/graphiti/.venv/bin/pip install -r implementations/graphiti/requirements.txt
docker run -d --name graphiti-neo4j -p 17687:7687 \
  -e NEO4J_AUTH=neo4j/test-password \
  neo4j@sha256:5a015e53de1895e7eee1574ae0325cf8c4b89587222778108c594bdd45a474b5
```

The pinned SDK is `graphiti-core==0.17.9` (Apache-2.0), Neo4j server is `5.26.0` Community Edition (GPL-3.0), and Python driver dependency is `neo4j==6.4.1` (Apache-2.0). Graphiti Core 0.17.9 has Neo4j and FalkorDB drivers; it does not ship the previously supported Kuzu driver or a Kuzu extra. No paid/provider inference was used.

Run the backend integration tests with:

```sh
PYTHONPATH=implementations/graphiti implementations/graphiti/.venv/bin/python \
  -m unittest implementations/graphiti/test_adapter.py -v
```

Close the adapter with `adapter.close()` when finished. The local Neo4j credentials and Bolt port are benchmark defaults for this synthetic pilot, not production credentials.

The final pilot trace is `results/graphiti/retrieval.jsonl`; its initial pre-hardening trace is preserved at `results/graphiti/runs/initial/`. The final run scanned 1,000 files / 254,560 bytes per adapter setup and reported 320 ingestion driver calls (schema index creation and episode writes/metadata/supersession updates); embedding calls were zero. Query file reads and bytes are zero because each query reads graph records only. The exact Neo4j image digest and local image ID are in `results/graphiti/backend-provenance.json`.
