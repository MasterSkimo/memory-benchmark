# Agentic Memory BENCH-0001 — Codex Cloud

Compare **Basic Memory, Cognee, Graphiti, Qdrant hybrid and Luna reading Markdown directly**. Primary metrics: grounded accuracy, citations, input/cached/output tokens, tool calls, cold-ingestion overhead, isolation and p95 latency.

## Start in Codex Cloud

1. Connect this GitHub repository to **Codex Cloud** and open a task on `main`.
2. Configure its **setup script** as `bash scripts/cloud-setup.sh` (or let Codex invoke it at task start).
3. Start the task with the instructions in [PROMPT-CODEX-CLOUD.md](PROMPT-CODEX-CLOUD.md).
4. Review the **20-question pilot** before approving the full run.

The setup script works with Python 3.11+ and no Docker; it bootstraps the synthetic corpus. The cloud agent will install candidate engines in isolated environments **only when permitted**. Docker, nested Codex CLI/auth, outbound network and native subagent telemetry are **not assumed**.

## Reproducible offline smoke tests

```bash
bash scripts/cloud-setup.sh
python3 -m unittest discover -s tests -v
python3 -m benchkit.smoke
```

## Security/validity

- `fixtures/private/oracle.jsonl` is **not committed**. It is generated locally to `$BENCH_PRIVATE_DIR` for a separate evaluator; it must not be mounted into any model/worker context. Sharing a directory or the same OS identity is **not** a security boundary.
- Never expose secrets, model answer gold, candidate outputs, or another tenant's documents to workers.
- Global local Codex rules are not present in this new cloud environment, but account/organization instructions and policies still apply. Nothing here bypasses platform-enforced restrictions.
- All vendor adapters start **unimplemented**. Missing results must be marked BLOCKED, not simulated.
- Preserve raw instrumentation evidence and report absent token counters as `null`, not zero.
- No real client documents, OpenRouter charges, or unauthorised API credentials.

See [BENCH-0001.md](BENCH-0001.md), [WORKER-CONTRACT.md](WORKER-CONTRACT.md) and [PROMPT-CODEX-CLOUD.md](PROMPT-CODEX-CLOUD.md).
