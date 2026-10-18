# Experimental results

The real implementation pilot is complete with stage limitations. See
[COMPARISON.md](COMPARISON.md), [run-manifest.json](run-manifest.json), and the root ADR.

Basic Memory, structured Graphiti/Neo4j, and non-neural Qdrant hybrid each have a
real, corpus-hash-verified 20-question retrieval pilot. Direct Markdown has 20
fresh native Luna answer sessions with audited filesystem operations and pre/post
corpus hashes. Cognee has source and tests but ingestion is blocked by a tokenizer
asset HTTP403; its earlier failed attempt is excluded from comparison.

Initial runs are retained under qualified `runs/` folders, including the shared
corpus mutation incident. They are not blended into final metrics. No bulk
NOT_RUN placeholder traces or generated gold are included. Native usage fields
remain null; wrapper calls and file I/O are separate measured counters.

Validate saved evidence with `python3 -m benchkit.validate_results`. Regenerate
the comparison/ADR from closed traces with `python3 scripts/finalize-pilot.py`.
