# Codex Cloud Task — BENCH-0001

Act as SOL coordinator using the Codex Cloud environment connected to this GitHub repository.

## Setup and capability discovery

1. Run `bash scripts/cloud-setup.sh`, then `python3 -m unittest discover -s tests -v`.
2. Inventory cloud tools: network, Python, Docker/container daemon (do not assume), Codex subagent delegation and CLI availability, model identity, counters, limits. Save `results/cloud-capabilities.json`.
3. Use the built-in Codex subscription/model access only. Coordinator SOL/high and workers Luna/medium **when supported**. If cloud aliases or agent tools differ, report exact observed identifiers; **never substitute another provider silently**.
4. Cloud workflows may not expose `codex exec --json` with nested login. If unavailable, capture task/subagent usage from supported native traces. Missing per-question data is `null` and coverage is reported; do not derive tokens from text length.
5. Fixture oracle is generated separately and must NOT be readable by candidate worker processes or model context. Before spawning workers, verify actual permission isolation. Sharing a repo Git worktree is insufficient.
6. Freeze seed, questions, versions, prompts, tool budgets and dataset hashes.

## Delegate independent candidate tasks concurrently if possible

- A: Basic Memory (Markdown roundtrip + retrieval + MCP).
- B: Cognee (graph/vector ingestion and retrieval).
- C: Graphiti (temporal graph and superseded decisions).
- D: Qdrant (dense+sparse search, tenant filters, citations).
- E: Codex Luna direct Markdown filesystem reads only (no index or RAG).

Each candidate owns `implementations/<candidate>/` and `results/<candidate>/`; no edits to shared corpus or grader. If five concurrent workers are not supported, run in waves and record concurrency faithfully.

## Experiment

- **R lane:** retrieved source IDs, revisions, recall/precision, latency and cross-tenant safety.
- **E lane:** same fresh Luna answer agent per question, identical prompt/tool policy, model and output format, actual tokens (input, cached and output), number/types of calls, retries, bytes, time and citations.
- Pilot: same 20 public questions per candidate. Record warm/cold separately.
- Indexing: count LLM and embeddings usage separately including graph extraction/rerank and failures; no hidden paid external providers.
- Compare token/call savings against direct vault Luna. Show Pareto frontier with latency and correctness, plus ingest cost amortized over 20/200/2k/20k queries.
- **STOP AFTER PILOT**. If candidate service or telemetry unavailable, report BLOCKED/INCOMPLETE with technical evidence, not measurements.

## Deliverables

A PR (or committed branch), `results/cloud-capabilities.json`, raw traces, run manifests, `results/COMPARISON.md`, and `ADR-0001-memory-benchmark-decision.md` with measured results and limitations.

Start now with capability discovery and offline tests, then delegate implementations. Do not claim you ran workers or measured tokens unless the underlying Codex Cloud tool supplied evidence.
