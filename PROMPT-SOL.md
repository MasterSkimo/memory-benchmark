# PROMPT SOL — BENCH-0001 Codex-native multi-Luna evaluation

You are **GPT-6.1 SOL running in Codex CLI**, using the user's **existing ChatGPT/Codex subscription**, not OpenRouter or an OpenAI API key. Coordinate five `gpt-6-luna` subagents concurrently to benchmark the memory mechanisms. Do not switch provider or model when authentication, rate limits or quota prevent an execution.

## Bootstrap and profile isolation

The operator must start you through `scripts/launch-sol.sh --reuse-auth` (or log in separately inside the isolated `CODEX_HOME`). This script:
- Builds a fresh repository under `/tmp/agentic-memory-codex.*/workspace`, away from user's global/project AGENTS instructions.
- Creates a **fresh CODEX_HOME** with only `config.toml`, a benchmark global AGENTS.md and optionally **auth.json only** copied by explicit user request.
- Does not copy the user's MCP servers, personal skills, plugins, memories, custom subagent definitions or config.toml.
- Leaves the project and original `~/.codex` untouched.
- Excludes `fixtures/private/oracle.jsonl` from the Codex agent workspace; scoring must happen in an independent evaluator environment.

**Boundary:** `CODEX_HOME` isolation avoids personal configuration, not operating-system permissions, organization-managed policy, or resource access outside a Codex sandbox. A Git worktree alone cannot shield an oracle from another same-UID process. Test data access using real container/filesystem restrictions, not prompts.

## Frozen model/provider contract

- Coordinator: `gpt-6.1-sol`, `high` reasoning, built-in OpenAI/Codex subscription provider.
- Candidate implementation agents: `gpt-6-luna`, `medium` reasoning, five subagents.
- End-to-end **answer agents in every candidate**: `gpt-6-luna`, `medium` reasoning. Use fresh Codex sessions per question and identical system/question framing.
- **No OpenRouter, API keys, LiteLLM proxy or paid per-request provider** for Luna/SOL. The user has not authorized them.
- Model names are **mutable aliases**: record `codex --version`, names, observed model/session metadata and execution time. Never claim immutable backend snapshots unless Codex exposes and verifies them.
- Identical tool description and prompt budgets where feasible. Do not let one candidate hide retrieval inside extra privileged tools without counting its internal calls.
- Some candidates (Cognee/Graphiti) may require their own ingestion LLM/embedding backend. Prioritize an authorized local implementation; identify unsupported paths and report `BLOCKED` rather than silently consuming a different paid account. Any authorized backend calls must be instrumented **separately**.

## Objectives

Choose the best memory method for durable project-owned Obsidian/Markdown/Git knowledge under project/tenant isolation: (A) Basic Memory, (B) Cognee, (C) Graphiti, (D) native Qdrant dense+sparse hybrid, (E) Codex Luna reading Markdown directly with `list/read/search` filesystem tools, **without an index**. Compare retrieval quality and answer quality, total Codex token usage, calls, file I/O, and elapsed time. Latency matters, but a slower option with significantly lower token and tool consumption can win if quality and isolation gates hold.

## Mandatory first steps

1. Read `BENCH-0001.md`, `WORKER-CONTRACT.md`, `AGENTS.md`, `README.md`, `config/codex/benchmark-budget.json`, `RFC-0001-Agentic-Platform-Architecture-V1.md`.
2. Confirm `CODEX_HOME` is isolated and `codex mcp list --json` has no unexpected global MCPs. Confirm `fixtures/private/oracle.jsonl` is absent in your workspace. Record the exact Codex CLI version and `RUN-MANIFEST.json` hash.
3. Freeze `fixtures/vault`, `questions_public.jsonl`, `manifest.json`, prompts and model settings. No regenerating fixtures to improve scores.
4. Before launching agents, prepare allowlisted worker copies (`benchkit.export_workers`) and place each candidate into a restricted service/data namespace. **If the worker OS process can access the oracle or a different tenant's secrets, record `ISOLATION_NOT_PROVEN` and block formal security acceptance.**
5. Perform offline integration tests and environment checks. Investigate packages/versions first, pin repository SHAs and container digests.
6. Launch five Luna subagents **in parallel**, one per candidate. Use `agents.max_concurrent_threads_per_session=5`. If the local Codex build/account cannot run five, use explicit waves and report actual concurrency.

## Delegation

| Luna | Candidate | Primary responsibility |
|---|---|---|
| A | `basic-memory` | Install Basic Memory, bidirectional Markdown integrity, MCP retrieval; assess AGPL implications |
| B | `cognee` | Ingest/cognify/search, graph/vector retrieval, account for ingestion-side LLM use |
| C | `graphiti` | Temporal decision history/obsolete revisions, graph backend and ingest traces |
| D | `qdrant-native` | Markdown sections, dense+sparse/RRF, tenancy filters, versioned citations |
| E | `luna-vault-direct` | Truly direct Codex Luna shell/file reads of authorized Markdown, no RAG, embeddings or indexed adapter |

Each worker owns only `implementations/<candidate>/` and `results/<candidate>/`. Use isolated Git worktrees plus separate services/ports/volumes. The dataset is shared **read-only**. No worker may edit the evaluator or other candidates' files. SOL integrates only committed changes and documents merge conflicts.

## Subscription quotas and soft stopping

Read `config/codex/benchmark-budget.json` for the configurable soft caps. They are **not** dollar budgets and do not enforce account quotas at the provider. Initial 5 × 20 pilot total: <=4,000,000 input tokens and <=300,000 output tokens; per candidate <=800,000 input and <=60,000 output; per question <=25 tool calls and <=12 model requests, where model request counts are instrumentable. Abort/stop at safe between-question boundaries when caps are reached or near; never claim per-turn hard limits without runtime support. Track coordinator/developer agent token consumption in a separate ledger from question-answer usage and ingestion. Do not consume the whole subscription during cold graph ingestion.

## Real Codex telemetry

- For each answer question start a fresh **`codex exec --json -m gpt-6-luna`** in the clean `CODEX_HOME`, with reasoning pinned `medium`, fixed permissions and a restricted authorized vault/tool set. This is an **evaluation harness**, not the interactive SOL launch.
- Preserve raw JSONL events. The kit provides `python -m benchkit.codex_trace --events ... --question-id ... --output ...` to normalize `turn.completed.usage` and `item.*` tool events. Extend the parser only when you have observed schema evidence and integration tests.
- Count `input_tokens`, `cached_input_tokens`, `output_tokens` and optionally `reasoning_output_tokens` (reasoning is a **subset of output**). Count unique agent tool-call IDs including failures, retries and tool types. Distinguish one MCP tool invocation from multiple internal backend RPCs.
- `cost_usd=null`: the ChatGPT subscription does **not** provide a reliable usage-based dollar price in Codex CLI traces. Do not convert tokens to an OpenRouter API estimate and present it as actual spend.
- Provider/model request count, cached token semantics, I/O and ingestion calls may require extra traces; if unavailable, record `null` and lower telemetry coverage. Don't infer `llm_calls` from `turn.completed`.
- Ingestion providers different from Codex must have their own cost/usage source, separately classified; if offline unavailable mark blocked, not measured.

## Controlled experiment

1. Run balanced **20-question** pilot for all five candidates, same question IDs, same Luna prompt and permissions.
2. Execute both Lane R (retrieval) and Lane E (Codex Luna answer). For direct-file Luna, Lane E is the authoritative baseline; a deterministic filesystem reader is merely a smoke comparator.
3. Measure correctness, citations with current revisions, abstentions, tenants, tool counts, I/O, cached/uncached token usage, latency and CPU/RAM. Run actual authorization-negative tests at the backend/MCP boundary.
4. Calculate cold ingestion costs separately; amortize over N={20,200,2000,20000} questions. Report unknown USD costs as N/A.
5. Keep identical usage counter conventions across lanes and per-question fresh sessions; collect 3 repeats if quota permits and label missing repetitions.
6. Do **not** start the remaining 190 questions, high-concurrency load test, or expensive paid embeddings automatically. **Stop after pilot** and present evidence/limits so the user can authorize the next phase.

## Deliverables

- `results/<candidate>/manifest.json`, `ingest.json`, `retrieval.jsonl`, `end_to_end.jsonl`, `LIMITATIONS.md`, raw Codex JSONL and instrumented backend calls.
- Scorer output created **only in a separate evaluator context with the private oracle mounted**, never by a candidate Luna.
- Comparison by answer quality, citations, zero-leak requirement, raw tokens, uncached-equivalent tokens, model calls (if verified), agent tool calls and time. Include a Pareto frontier, cost amortization and sensitivity to time/token preferences.
- `ADR-0001-memory-benchmark-decision.md` with measured results and explicit BLOCKED/INCOMPLETE classifications, if applicable.
- Integration-test evidence and SHA/config manifests.

Begin immediately with offline setup and five concurrent Luna implementations, then the 20-question pilot, stopping at its review gate. Never fabricate measurements or extrapolate raw API-dollar pricing to ChatGPT subscription usage.