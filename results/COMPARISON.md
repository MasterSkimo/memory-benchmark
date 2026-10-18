# BENCH-0001 — real implementation pilot

Five native `gpt-6-luna`/medium implementation workers ran concurrently. Three
actual backend variants completed the same twenty-question retrieval pilot;
twenty fresh native Luna sessions completed the direct-filesystem answer pilot.
Cognee has real adapter code but its ingestion remains blocked. No nested Codex
CLI, external inference provider, full benchmark or load test was used.

## P1R — retrieval measurements

| Tested variant | Successful queries | Recall@5 | Precision@5 | p50 / p95 ms | Leaks / revision errors / superseded hits |
|---|---|---|---|---|---|
| Basic Memory 0.13.1 / FTS5 | 20/20 | 100% | 24.29% | 3.47 / 4.33 | 0 / 0 / 3 |
| Graphiti 0.17.9 / structured Neo4j episodes | 20/20 | 100% | 24.29% | 6.55 / 8.01 | 0 / 0 / 0 |
| Qdrant client 1.15.1 / non-neural hybrid | 20/20 | 100% | 24.29% | 22.46 / 24.96 | 0 / 0 / 3 |
| Cognee 0.5.1 / Kuzu 0.11.3 / LanceDB 0.40.0 | 0 usable; blocked | N/A | N/A | N/A | NOT_TESTED |
| Luna direct filesystem | No separate deterministic R control | N/A | N/A | N/A | See native E evidence |

Recall and precision cover the 14 support-bearing questions; precision uses a
fixed denominator of five. All 14 had all required sources retrieved. All three
working retrievers also returned nonempty results for all six unsupported or
foreign-scope questions. **Source recall is not answer accuracy or abstention.**
Superseded hits have accurate metadata revisions but contain obsolete facts.

The observed retrieval-only frontier is **basic-memory, graphiti** on recall,
precision, obsolete-source count and p50/p95 query latency. This describes these
prototype variants in this one pilot; it is not a product/semantic-search winner.
Memory, tokens and native calls are excluded from dominance because comparable
measurements are missing. Basic Memory and Graphiti counters count outer SDK/DB
invocations; hidden driver/internal backend calls are not established by them.

## What actually ran

- Basic Memory: real parser, Markdown SyncService, project-scoped repositories
  and SQLite FTS5; a generic OR-term query adapter. The SDK may edit its input,
  so it receives a validated private copy. Source bytes remain authoritative.
  MCP/CLI startup remains blocked by FastMCP/MCP compatibility; Python SDK R works.
- Graphiti: genuine `EpisodicNode.save` and Graphiti Neo4j driver on pinned Neo4j
  5.26.0. Structured Markdown episodes, current-revision flags and lexical ranking
  are implemented. LLM graph extraction, embedding, Graphiti semantic search and
  temporal inference were not tested. This is not the full Graphiti pipeline.
- Qdrant: genuine embedded Qdrant dense+sparse prefetch and RRF with org AND project
  filters. Dense signed hashing and sparse term counts are non-neural controls,
  not pretrained semantic embeddings. Four scoped adapters each build an index;
  this prototype does not optimize a shared multi-tenant index lifecycle.
- Cognee: pinned real add/cognify/CHUNKS integration code. `add` is blocked before
  storage by a static tiktoken asset HTTP 403. Five checks pass; the actual vector
  retrieval test skips. Successful ingestion, dataset-ID resolution, graph/vector
  retrieval and backend isolation are **unverified**. Local inference is explicitly
  opt-in and loopback-only; no alternative provider was introduced. Its earlier
  twenty failed attempts used a modified corpus and are excluded from comparison.
- Direct vault: no index, embeddings or graph. Native Luna sessions use audited
  scoped list/read/search over Markdown; the lexical filesystem helper alone is
  not presented as Luna. The standalone deterministic R control was not run.

## P1E — native direct-vault answers

| Variant | Fresh verified sessions | Canonical components + exact source citations | Strict string equality | Out-of-scope / wrong-revision citations | Native tokens / full latency |
|---|---|---|---|---|---|
| Luna direct Markdown | 20/20 | 100% | 65% | 0 / 0 | NOT_AVAILABLE |
| Other backends | No comparable E harness | N/A | N/A | NOT_TESTED | NOT_AVAILABLE |

Component scoring is the declared deterministic canonical-value containment plus
all required exact-revision citations; it is not human semantic evaluation.
All unsupported/unauthorized baseline questions abstained. Responses were graded
only after sessions closed. Native runtime cannot enforce a restricted capability
set or export exact tokens/tool counters/full wall time here. The E observations
use prompt binding and actual wrapper audit; they do not establish strict tool
parity or hostile-shell authorization. API tests enforce scope for a bound
principal instance; a production service must bind that principal outside model
control. Backend answer pilots were not substituted with SOL or lexical answers.

Token coverage is **0/20** completed verified answers.
Input/cached/output/reasoning tokens, actual USD, model requests, retries, native
tool counts and full-session latency remain null. The model alias/effort selected
by native delegation is recorded; immutable served snapshots and coordinator
SOL/high identity are not independently exported. Wrapper calls are a separate
instrumented layer: 21 successful file-tool operations,
2,100 source reads and 536,676 UTF-8 bytes.
Integrity guards additionally scanned 42,000 files /
10,691,520 bytes. These costs are recorded separately,
and must be included when assessing total benchmark I/O. The guard computes a
trusted corpus digest; it returns no cross-tenant source content to Luna.
Wrapper/operation durations are not native end-to-end latency.

## Ingestion, caching and cost

Per-scope factory setup and known ingestion I/O are in each `ingest.json` and
`retrieval-summary.json`. Factory timing includes initialization/validation/sync,
not solely indexing. Qdrant/Graphiti each read the 1,000-file corpus per factory;
Basic Memory's internal sync I/O is not exported. The tested variants do not
invoke extraction/embedding/rerank models; Cognee stops before those stages.
No reported provider token/cost events exist for index or answer consumption.

| Workload queries N | Token savings vs direct | Native-call savings | Ingest + answer tokens/USD amortized |
|---|---|---|---|
| 20 | N/A | N/A | N/A |
| 200 | N/A | N/A | N/A |
| 2,000 | N/A | N/A | N/A |
| 20,000 | N/A | N/A | N/A |

The future formula is ingest usage/N plus per-answer input+output; cached input
and reasoning are overlapping breakdowns. No zero or text-length proxy replaces
missing usage. First-scope vs reused-adapter query groups are separate in the
summaries; OS caches are uncontrolled, so these are not true cold/warm-cache
experiments. Setup and integrity-check I/O are excluded from query durations and
identified separately. Process CPU/RSS is captured where available; Neo4j server
memory/CPU and physical disk I/O are not included in its Python process counters.
Implementations/other workstreams shared resources, so timings are descriptive,
without confidence intervals or throughput claims.

## Integrity, source and reproducibility

The requested corrective branch accidentally removed setup/generator/tests; those
were restored from its parent `6e1dcee`. The same public seed42/cloud-0.2 corpus,
questions, policy and limits were frozen before workers. The corpus digest is
`644b954c4ffe3dbe255e03fe3c24eb9e7bf7248db3790edfeba3ae2bc311e716`.

An initial Basic Memory sync added permalink metadata to 400 shared notes.
That run is invalid. Cognee's failed attempt and the initial direct observations
are also explicitly qualified, rather than blended into final measurements.
The corpus was restored, Basic Memory changed to private-copy sync, and final R
pilots verify hashes before setup, after every factory and after execution. Final
native E tools verify the exact hash before/after every operation. Only the same
twenty IDs were repeated after these fixes; all earlier actual traces remain
under qualified `runs/` directories. See `corpus-integrity-incident.json`.

Real integration tests cover org/project request tampering, shared-backend foreign
sources, exact revision updates and forged provenance; direct tools additionally
test path traversal/symlinks/call budgets/integrity failures. Cognee's backend
isolation is not proven while storage is blocked. No secret holdout is claimed:
the scorer/generator are public, the pilot uses four alpha projects and only the
first variant of each category, and synthetic answers repeat. A withheld,
human-reviewed corpus and comparable embedding/extraction configuration are
required before a product decision.

Reproduction: candidate READMEs and pinned locks, `results/frozen-pilot.json`,
`results/run-manifest.json`, real JSONL/events, `results/reproducibility.json`.
Run `python3 -m unittest discover -s tests -v` and
`python3 -m benchkit.validate_results`; final consolidation is
`python3 scripts/finalize-pilot.py` after actual candidate traces close. No full
190-question, mutation or load phase is authorized or executed.
