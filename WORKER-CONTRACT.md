# Worker contract — one Luna per candidate

Each Luna receives **one candidate**, the frozen public questions, the same neutral runner and the same instruction template. One worker cannot rewrite benchmark fixtures, the oracle, neutral scorer, the common model config or other candidate implementations.

## Worker assignments

| Worker | ID | Path | Responsibility |
|---|---|---|---|
| Luna A | `basic-memory` | `implementations/basic-memory` | Install/pin Basic Memory; test Markdown round-trip and MCP; instrument |
| Luna B | `cognee` | `implementations/cognee` | Ingest/cognify/retrieve; account for ingestion LLM and graph calls |
| Luna C | `graphiti` | `implementations/graphiti` | Build temporal graph; test obsolete/current facts, track episode LLM calls |
| Luna D | `qdrant-native` | `implementations/qdrant-native` | Implement Markdown section extraction, hybrid RRF, source revisions and metadata filters |
| Luna E | `luna-vault-direct` | `implementations/luna-vault-direct` | Only Luna and filesystem list/read/search tools; no index or semantic search |

## Inputs (read-only)

- `BENCH-0001.md`, `WORKER-CONTRACT.md`
- `fixtures/vault`, `fixtures/questions_public.jsonl`, `fixtures/manifest.json`
- `benchkit/runner.py` and the documented Python adapter contract
- Immutable Luna/provider profile and authorization scope supplied by SOL

**Do not allow agents to open:** `fixtures/private`, other candidates' results, previous answer traces, or generated gold-score reports. A file existing in the Git repository is not an acceptable security barrier: omit it from the mounted/mapped worktree for workers.

## Mandatory deliverables

1. A reproducible setup with pinned versions/digests and no hardcoded secrets.
2. A functional adapter exposing `search(question, top_k)`, returning `hits`, `file_reads`, `bytes_read`, `tool_calls`, `backend_calls`, `llm_calls`, and `usage` (null if unavailable).
3. A normalized Luna end-to-end execution path capable of collecting **raw usage and tool calls per question**, separate from search adapter CPU/time metrics.
4. A real 20-question smoke run (or explicit `BLOCKED` with steps to reproduce), without invented results.
5. Project/tenant isolation tests and update/revision tests; negative tests must fail correctly.
6. `results/<candidate>/manifest.json`, `ingest.json`, raw event files, `retrieval.jsonl`, `end_to_end.jsonl`, `LIMITATIONS.md`.
7. No cross-project edits. Commit all changes in the candidate's worktree and notify SOL of commit SHA.

## Interfaces

Adapter code implements:

```python
# The actual worker module must declare its imports and handle project scoping.
class CandidateAdapter:
    def __init__(self, corpus):
        # Initialize private candidate state without reading the oracle.
        ...

    def search(self, question: dict, top_k: int = 5) -> dict:
        # Return document IDs and exact source revisions in hits.
        ...
```

Do not report proxy usage as actual usage; missing internal counters remain `null`. The Luna direct-file candidate must not import or reuse `FileAdapter` as its search engine: it uses real Luna tool interactions.

## Stop conditions

- Abort tenant leak tests immediately, capture sanitized evidence and inform SOL.
- Abort if a backend unexpectedly transmits data to an unauthorized external service.
- Respect per-worker token and monetary budgets; no speculative broad paid ingestion.
- Never flatten all Markdown into Luna's initial prompt, unless explicitly running a separate declared "dump all context" anti-baseline.

## Codex-native worker contract amendment

- Every implementation worker is a Codex `gpt-6-luna` subagent at `medium` reasoning, not an OpenRouter API worker.
- Use isolated Codex home and controlled launcher. Do not load or copy user-level model configuration, MCPs, skills, memory, rules or profiles.
- Do not change the common Luna answer model in your candidate lane. Do not pass ChatGPT credentials or Codex `auth.json` into Docker images, logs, or result artifacts.
- For end-to-end benchmark traces use *actual* Codex `exec --json` event files and normalize them with `benchkit.codex_trace`. Keep unknown usage fields at `null`, including USD cost and LLM request counts that the CLI does not expose.
- Respect the soft question and pilot limits in `config/codex/benchmark-budget.json` and stop after the 20-question pilot.
- For tools/plugins/MCPs needed by a candidate, declare them **only in the candidate's isolated runtime**, not in the user's global Codex profile. The underlying retrieval services may expose MCP interfaces but must be scope-limited to one test project/tenant per question.
- Some packages require embedding/LLM calls for ingestion; do not silently switch to a paid external provider. Record blocked offline functionality honestly.