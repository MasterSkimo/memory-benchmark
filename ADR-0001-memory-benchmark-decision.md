# ADR-0001 — Preserve Markdown ownership and a scoped retrieval boundary

Date: 2026-10-18. Status: **Pilot decision; product engine selection deferred**.

Keep project Markdown/Git as authoritative knowledge. Place a narrow read API in
front of rebuildable indexes, bind organization/project from trusted caller
authorization, and return document ID plus exact revision. SDKs that mutate
Markdown must ingest private working copies. Verify corpus integrity around
ingestion and keep native answers separate from retriever metrics.

This decision is backed by actual code/tests and three verified twenty-query
pilots: Basic Memory FTS5 (3.47 ms p50),
structured Graphiti/Neo4j episodes (6.55 ms), and
non-neural Qdrant hybrid (22.46 ms).
Each retrieved all required sources on the fourteen support-bearing questions,
with zero observed out-of-scope hits or revision mismatches. Graphiti suppressed
all obsolete notes; Basic Memory and Qdrant returned three superseded hits each.
All three returned results on unsupported/foreign questions, so retrieval alone
does not establish safe answer abstention. The observed R-only frontier is
basic-memory, graphiti; it cannot rank the full semantic products.

Twenty fresh native Luna direct-file sessions produced
100% grounded canonical-component matches and
65% strict string matches, with correct abstention and
no observed wrong-scope/revision citations. Native capability restriction and
per-question tokens/native calls/full latency are unavailable; these are
observational answers, not a complete comparable E benchmark. Token savings,
native-call savings, monetary costs and 20/200/2k/20k usage amortization remain N/A.

Basic Memory MCP startup is separately blocked by package compatibility. Cognee
has an adapter and five passing checks, but tokenizer HTTP403 blocks ingestion;
its real retrieval test skips and backend isolation/provenance are unverified.
Graphiti uses structured episodes/custom lexical ranking without graph extraction
or temporal inference; Qdrant uses explicit local hashing rather than neural
embeddings. These choices avoid paid providers but limit product comparisons.

An initial SDK sync modified shared metadata. The public corpus was restored,
the writing SDK now receives a private copy, and final traces have hash guards.
Earlier runs are preserved and qualified. This incident is implementation
evidence for the ownership boundary, not a retrieval-quality result.

Do not select a final vendor from this small, public, repeated-answer synthetic
pilot. After review, validate comparable local semantic/extraction models, repair
the blocked MCP/Cognee stages, expose authenticated scoped read services, and
evaluate a withheld human-reviewed corpus. This run stops at the frozen twenty
questions; full/read mutation and concurrent-load phases still require review.

Evidence: [comparison](results/COMPARISON.md), [manifest](results/run-manifest.json),
[integrity incident](results/corpus-integrity-incident.json),
[frozen inputs](results/frozen-pilot.json), and each candidate's source/tests/events.
