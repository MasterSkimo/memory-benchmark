# BENCH-0001 — Comparative benchmark for project-owned agentic memory

| Field | Value |
|---|---|
| Status | **Executable protocol, results pending** |
| Date | 2026-10-18 |
| Target | Knowledge Runtime decision for RFC-0001 |
| Primary question | Which approach supplies **grounded answers** with the lowest effective token consumption and tool-call count, subject to strict isolation? |
| Systems | Basic Memory, Cognee, Graphiti, native Qdrant hybrid, Luna reading Markdown files directly |
| Separate sanity control | Deterministic filesystem keyword retriever (not the Luna baseline) |

## 1. Decision criteria and hard constraints

**Non-negotiables (a candidate fails if unmet):**

1. Persistent knowledge is **Markdown/Git owned by each project**. An index may be reconstructed and removed without losing authoritative knowledge. Candidates that store knowledge primarily elsewhere must provide a demonstrably lossless export/rebuild adapter, or be marked as requiring significant integration work.
2. A search for project A cannot retrieve material from unauthorized project B or another organization. Filter **before retrieval**, not in the LLM prompt. Test direct tool/API access and alternate identifiers.
3. Every factual answer identifies its source document and revision, even when the candidate's native API does not provide provenance (in that case, report an adapter workaround).
4. Run self-hosted, with external LLM/embedding providers **optional**. Document and isolate any forced external transmission.
5. Agent clients connect through a narrow MCP or equivalent read interface; the benchmark does not grant arbitrary write access.
6. No ingestion of live Jenkins, SonarQube, Jira or other volatile state for this test. Only curated durable notes.
7. No candidate may read `fixtures/private/oracle.jsonl` during execution.

**Optimization after gates:** grounded answer accuracy → no hallucinated confident answers → low tokens + tool calls → ingestion cost → latency → operational complexity. Do not award a fast but inaccurate/unsafe candidate.

## 2. Candidate systems

| ID | System | Scope | Source |
|---|---|---|---|
| `basic-memory` | Basic Memory | Markdown sync, MCP, semantic/linked search | https://github.com/basicmachines-co/basic-memory |
| `cognee` | Cognee | Cognify, graph/vector extraction, retrieval | https://github.com/topoteretes/cognee |
| `graphiti` | Graphiti | Temporal graph, episodes, search | https://github.com/getzep/graphiti |
| `qdrant-native` | Qdrant hybrid | Section chunks, dense+sparse, metadata and citations | https://qdrant.tech/documentation/search/hybrid-queries/ |
| `luna-vault-direct` | Luna with direct Markdown | Filesystem read/list/search tools; **no persistent search index** | Controlled baseline |
| `baseline-files` | Deterministic lexical scan | Debug-only control (no LLM); cannot win end-to-end | Bundled adapter |

Pin each external candidate to an immutable Git SHA or Docker digest and attach a license assessment. Basic Memory's public repository currently lists AGPL-3.0; validate commercial integration obligations independently. Do not assume all candidates have the same native API or equivalent Markdown ownership.

## 3. Benchmark dataset

The repository contains a deterministic synthetic generator (`benchkit/generate.py`) that builds:

- `fixtures/vault/`: **1,000 Markdown files**, 2 organizations × 5 project Knowledge Spaces × 100 files. Front matter includes stable `document_id`, organization, project, status and revision. Notes include deliberate distractors and `[[wikilinks]]`.
- `fixtures/questions_public.jsonl`: **200 prompts** (20 per space), without answers or ground-truth citations. This is the **only** input provided to candidates.
- `fixtures/private/oracle.jsonl`: answers, authoritative document references, forbidden references, categories and abstention expectations. **Never mount into agents, candidate containers or memory services.**
- `fixtures/manifest.json`: corpus seed and declared dimensions.

Per Knowledge Space, questions include 4 exact identifiers, 4 semantic reformulations, 3 two-document relations, 3 superseded/current decisions, 2 not-present questions, 3 unauthorized-source probes, and 1 concurrent-write scenario. Totals: 190 answer/retrieval questions + 10 write-concurrency scenarios.

**Important limitation:** synthetic generated notes do not prove real-world retrieval quality. Run a second, independently curated and manually reviewed corpus of sanitized operational/architectural documents, only with documented client authorization. Keep project ACLs and mixed-language (French/English/Spanish) documents in that second phase.

**Gold independence:** Luna/other candidate agents never receive the oracle, its supporting document IDs, private fixtures, scoring implementation, expected answers or evaluation output from previous candidates. Scoring happens after traces are closed. Even the synthetic generator must not be used to infer answers during the run.

## 4. Two evaluation lanes + three lifecycle phases

### Lane R — Retriever only

Send identical question and authorized `organization_id`/`knowledge_space_id` to each engine via a normalized read-only adapter. Return up to `top_k=5` chunks with `document_id`, `revision`, `score`, `text`. Measure recall, precision, completeness of evidence, tenant leaks, query latency and backend CPU/RAM. This lane isolates search quality from Luna's reasoning.

The filesystem adapter is a minimal lexical smoke baseline and deliberately reads all files in the authorized space. It does **not** model Luna's normal file-tool use.

### Lane E — Luna end-to-end, **same model for all candidates**

Start a **fresh Luna session for each question** (avoid cross-question memory contamination), same system prompt, model snapshot, reasoning effort, decoding settings, MCP/tool description budget and token budget. All access to the vault is through one of:

- Native candidate tool(s) with read-only project scoping; or
- For `luna-vault-direct` only: authorized filesystem tools `list`, `read` and `search` (or equivalents) on the Markdown files. **No Qdrant, graph, semantic index or external search.**

Compare: exact/semantic answer correctness, factual abstention, citation correctness, tools actually called (count and names), input/output/cached/reasoning tokens, output context size, wall time and LLM errors. Record backend requests hidden behind one MCP call separately: one visible tool call is not always one backend request.

### Phases

- **P0 Cold ingest:** empty store, full import/index, CPU/RAM, I/O, elapsed time, LLM extraction calls and all embedding/token/cost use. Measure failed/retried chunks.
- **P1 Warm steady state:** retrieval/answer against a completed index, warm caches, 1 concurrent user. Record full per-question telemetry.
- **P2 Concurrency:** same questions, increasing to 5 then 20 concurrent agent sessions (per candidate), isolate resources/provider quotas and record p50/p95/p99. Run candidates sequentially or allocate isolated fair pools so they do not compete on the same infrastructure.
- **P3 Update and integrity:** append/change/delete notes, old-to-new decision replacement, simultaneous writes and delayed index visibility; measure rebuild and freshness. Write conflicts must fail safely or require user reconciliation; no silent overwrite.

Use a 20-question pilot first (balanced categories), then the full 190 read questions. The 10 mutation scenarios use a separate protocol and do not count toward answer accuracy.

## 5. Telemetry contract (mandatory)

Every answered question yields one JSONL trace. Example:

```json
{
  "question_id": "q00-exact-0",
  "lane": "end_to_end",
  "status": "ok",
  "answer": "42 minutes",
  "citations": [{"document_id": "org-alpha/project-01/note-010", "revision": "synthetic-010"}],
  "hits": [{"document_id": "org-alpha/project-01/note-010", "score": 0.93, "revision": "synthetic-010"}],
  "duration_ms": 5600,
  "tool_calls": 2,
  "llm_calls": 3,
  "file_reads": 0,
  "bytes_read": 0,
  "context_bytes": 1024,
  "usage": {
    "input_tokens": 3500,
    "cached_input_tokens": 500,
    "output_tokens": 300,
    "reasoning_tokens": 150,
    "cost_usd": null
  }
}
```

**These values are a schema example, NOT measurement results.** Keep literal `null` for unavailable telemetry and attach raw provider/agent events for independent verification. `reasoning_tokens` is generally a **subset** of output tokens; never add it again. `cached_input_tokens` is generally a **subset** of input tokens; check each provider's convention first.

Capture separately:

- `tool_calls`: calls made **by Luna** to tools/MCP/file APIs, including failed/retried calls. Also collect distribution by tool and count of returned tokens/bytes.
- `llm_calls`: actual requests to models by the answer agent (and any retrieval sub-LLMs if used). Include pre-processing or reranking/model use separately.
- `backend_calls`: RPC/API calls internal to each memory engine, reported separately from Luna tool calls.
- `input_tokens`, `cached_input_tokens`, `output_tokens`, `reasoning_tokens` and actual reported `cost_usd` per model/provider. Use model-level accounting if engines call distinct models internally.
- `file_reads`, `bytes_read`, read syscalls if available, request counts, disk/network bytes; distinguish container-local OS cache vs physical I/O when possible.
- `elapsed`, queue time, model wait, index/search time; CPU seconds, peak RSS and failures (including throttling/429).

### Token definitions — compare without double counting

- **Raw tokens per answer:** `input_tokens + output_tokens` (all requests including retries and auxiliary LLMs in the chosen accounting scope).
- **Uncached-equivalent tokens per answer:** `input_tokens - cached_input_tokens + output_tokens`. This is a **proxy**, not a provider-independent billing rule.
- **Reasoning tokens:** report as **breakdown** of output, **not** additive.
- **Provider-billed cost:** use itemized actual usage/pricing when available; do not invent it from counts.
- **Effective total workload cost:** amortize `ingest_tokens` over `N` answered queries and add per-query usage, for `N=20, 200, 2,000, 20,000`; repeat for reported monetary cost where possible.
- **Telemetry coverage:** fraction of traces with verified token/tool counters. Incomplete telemetry is `N/A`, **never** zero.

Caching must be measured both **cold** and **warm**. Record cached input, dynamic context tokens and any cache invalidation triggered by a changed note.

## 6. Evaluation metrics

| Axis | Metrics |
|---|---|
| Answer | exact-answer correctness, abstention rate, unsupported/confident answer rate, citation correctness |
| Retrieval | recall@5/@10, precision@5, all-required-sources retrieved, wrong-version retrieved |
| Security | cross-tenant/cross-space leakage = **zero**, forbidden tool attempt outcomes |
| Resource usage | raw tokens, uncached-equivalent tokens, cost, Luna tool calls, engine internal RPCs, file bytes read |
| Runtime | p50/p95/p99 end-to-end latency and retrieval latency; throughput at 1/5/20 concurrency |
| Lifecycle | indexing tokens and elapsed, incremental ingestion, storage size, document updates, stale results, rebuild/import/export |
| Operations | components, complexity, license, offline mode, ability to preserve Markdown/Git authority |

For the first comparison, use a **Pareto view** rather than one opaque composite score. Candidate X dominates Y only when it meets quality/security gates, has no lower accuracy, and is better in at least one of effective tokens, tool calls or latency without being worse on the others. Retain non-dominated candidates. Users may set preference weights later.

**Preliminary gates (targets, not measured facts):** 0 leaks, 100% of supported conclusions traceable to current source, verified telemetry coverage ≥ 95%, wrong/unsupported confident answers < 2%, grounded answer accuracy ≥ 90% on the synthetic set. The latter thresholds are configurable and subject to calibration on a human-reviewed corpus.

## 7. Fair experiment controls

1. Freeze versions, prompts and embedding models; record code SHA, temperature, retrieval top-k, cache conditions and model config per run.
2. Match the **same underlying knowledge and effective permissions**. A system that silently reads all tenants fails irrespective of accuracy.
3. Do not let agents see the oracle or outputs from competitors. Use one candidate folder per Luna worker.
4. Keep model reasoning and output limits constant; don't silently give one candidate more exploratory turns.
5. Both backend-native indexing and agent read costs count. If an engine executes hidden LLM calls during ingest, record them.
6. Cap pilot consumption, abort on runaway loops, inspect retries and 429s. Split workers across independent backend endpoints/providers where necessary.
7. Gather ≥3 repeats on representative questions with different random seeds when model supports them; report variation, not one lucky score.
8. Preserve failures and missing results. Missing traces must not be treated as successful abstentions.
9. Benchmark actual isolation through direct API attempts, not prompt instructions alone.
10. Never edit gold answers to make a candidate look better; document ambiguous/incorrect oracle cases and version a corrected dataset.

## 8. Operational artifacts per candidate

```text
implementations/<candidate>/
  README.md           # exact setup, source SHA, license and limits
  adapter.py          # normalized search interface (if supported)
  deploy/             # optional compose/manifests, isolated ports and secrets
results/<candidate>/
  manifest.json       # engine/model/build versions, hardware, settings, corpus hash
  ingest.json         # ingestion operations/resources/tokens/cost
  retrieval.jsonl     # normalized Lane R traces
  end_to_end.jsonl    # normalized Lane E Luna traces
  updates.jsonl       # lifecycle/isolation/update test traces
  events/             # raw Luna/model/MCP tool events (redacted)
  score.json          # common evaluator output
  LIMITATIONS.md      # unsupported features + observed issues
```

`benchkit.runner` currently supplies a real neutral filesystem adapter, the JSONL schema, and an executable scorer. Candidate adapters, actual Luna executor/event parser and deployment manifests are **assigned to the Luna workers**. Do not claim their benchmark results exist until they have executed.

## 9. Execution plan

1. SOL pins benchmark protocol, dataset hash and immutable pilot subset. Freeze `benchkit`, fixtures and oracle.
2. SOL creates five isolated worktrees and delegates one candidate to each Luna (Basic Memory, Cognee, Graphiti, Qdrant hybrid, Luna direct Markdown).
3. Workers prepare only their adapter/deployment/manifest, run contract tests, and then the 20-question pilot; report errors and limitations honestly.
4. SOL reviews candidate parity, token instrumentation and project isolation. Integrate worktrees without changing the frozen oracle.
5. SOL executes full read dataset and 1/5/20 concurrency phases as budgets allow. If capacity/budget prevents completion, mark those phases `NOT_RUN`.
6. SOL computes normalized reports (including ingest amortization), presents the Pareto frontier, and writes ADR recommendation with explicit evidence and remaining gaps.

## 10. Sources / technology checks

- Basic Memory repository and MCP tooling: https://github.com/basicmachines-co/basic-memory
- Cognee ingestion and API: https://github.com/topoteretes/cognee and https://docs.cognee.ai/api-reference/introduction
- Graphiti MCP and database prerequisites: https://help.getzep.com/graphiti/getting-started/mcp-server
- Qdrant hybrid RRF: https://qdrant.tech/documentation/search/hybrid-queries/
- OpenCode CLI token stats/session export (if used to run Luna): https://docs.opencode.ai/docs/cli/

**Note:** API and CLI signatures evolve. Each Luna must pin and verify the current version and create integration tests against that version before launching paid model runs.