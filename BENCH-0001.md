# BENCH-0001 — Durable project-owned agentic memory (Codex Cloud revision)

Status: **Protocol v1.1 — implementation pilot pending**. The earlier Cloud branch produced environment diagnostics only; no engine was benchmarked.

## Objective

Determine which mechanism returns correct, cited durable Markdown/Git knowledge with minimal Luna tokens, tool calls, I/O and acceptable latency: Basic Memory, Cognee, Graphiti, Qdrant hybrid or direct vault reads by Luna.

## Dataset and scope

`bash scripts/cloud-setup.sh` generates 1,000 synthetic Markdown notes in two organizations × five projects, 200 public questions (190 read and 10 mutation). The 20-question pilot is fixed in `fixtures/questions_public_pilot.jsonl`; freeze questions, seed and manifest hash for each run. This is an **open synthetic development corpus**, because generator/scorer are public in the source tree; a withheld, human-reviewed corpus must follow before a product decision.

## Two independent security notions

**Tenant/project boundary (mandatory):** every candidate must enforce org/project authorization before retrieving and returning results. Test API access to out-of-scope data; any real cross-project leak disqualifies candidate.

**Development worker isolation (not a blocker):** native Codex implementation workers may share an OS UID and can operate on the same synthetic source tree. Use worktrees for avoiding source conflicts. Lack of strong worker filesystem isolation cannot prevent implementation or R-lane testing. Worker prompts prohibit looking up gold; these prompts are not a blind-evaluation guarantee.

## Candidate lanes and phases

| Candidate | Implementation |
|---|---|
| basic-memory | Markdown round-trip / scoped search / MCP |
| cognee | graph/vector ingestion and retrieval |
| graphiti | temporal graph, revisions and supersession |
| qdrant-native | hybrid dense+sparse, Qdrant tenant filters |
| luna-vault-direct | native Luna with only filesystem list/read/search, no index |

**P0 — Real implementations:** SDK installs, dependency pins, adapters and integration tests. Use native Luna subagents concurrently where supported; each writes a disjoint candidate folder.

**P1R — Retriever-only:** same 20 pilot questions, top-k 5, authorized org/space, actual hits and citation IDs/revisions, leakage, latency p50/p95, backend calls and file I/O. This phase NEVER requires nested Codex CLI or Luna token telemetry.

**P1E — Luna answers:** same native Luna model/effort and instructions/tools, 20 fresh sessions per candidate **where possible**. Capture true tokens (input, cached, output, reasoning breakdown), tool calls, retries, citations and answer correctness. If native per-question model/token/tool export is not possible, mark missing counters N/A instead of blocking R.

**P2/P3 — Future:** full 190 questions, 10 concurrent mutation tests, 1/5/20-agent load and robustness. NOT authorized until pilot review.

## Measurement rules

For every **executed** question: record candidate ID, question ID, lane, status, retrieved source IDs/revisions/scores, answer/citations when available, end-to-end milliseconds, backend calls, file reads/bytes and model/tool usage when measured. Unknown = `null`, never 0.

- `reasoning_tokens` is generally a subset of output tokens, not additive.
- `cached_input_tokens` generally overlaps input tokens; verify provider semantics.
- Index/graph extraction, local embedding, rerank and answer model cost must be separate.
- Do not convert characters to "measured tokens". No invented USD costs for Codex subscription.
- Do not conflate an MCP tool call with internal backend RPCs.
- Compare different embedding/extraction choices with explicit caveat if they cannot be held constant.
- Compare correctness/provenance and tenant leaks even if end-to-end token coverage is incomplete.

Report separate P1R and P1E tables. Claim Pareto dominance only for comparable measured axes; calculate indexing amortization for 20/200/2,000/20,000 queries only if actual costs/tokens are observed.

## Artifacts and exit criteria

Keep reproducible implementation source, integration tests, candidate manifests, redacted concise `results/COMPARISON.md`, `results/run-manifest.json`, ADR and any real traces. Do NOT commit secrets, raw environment/network/auth dumps or 40 dummy NOT_RUN rows per candidate. A single concise blocker suffices if a particular engine cannot start.

**Success requires tested implementation code for at least one candidate, statuses for all five, and a retrieval pilot to the extent permitted. Stop after 20-question pilot.**
