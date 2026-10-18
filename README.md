# Agentic Memory — BENCH-0001 / Codex Cloud

Compare **Basic Memory**, **Cognee**, **Graphiti**, **Qdrant hybrid**, and **native Luna reading a Markdown vault directly**. Compare retrieval, citations, cross-project leakage, latency, I/O, and measured (where available) Luna token/tool usage.

## Run in Codex Cloud

1. Open this GitHub repository in Codex Cloud on branch `fix/codex-cloud-real-pilot` (or merge the corrective PR first).
2. Configure its setup script as `bash scripts/cloud-setup.sh` if offered.
3. Create a task with [PROMPT-CODEX-CLOUD.md](PROMPT-CODEX-CLOUD.md), using SOL/high coordinator and native Luna/medium workers where supported.
4. Stop and review the 20-question pilot; do not run full/load tests yet.

## Offline setup

~~~bash
bash scripts/cloud-setup.sh
python3 -m unittest discover -s tests -v
python3 -m benchkit.smoke
~~~

Python setup requires no API key, Docker, or nested Codex CLI. Candidate backends are installed and tested independently by the workers. Generated `fixtures/` is ignored by Git; freeze the manifest hash for each run.

## Scientific limitations

- This synthetic dataset and its scorer implementation are both **public**. It is suitable for development/integration tests but is NOT a blinded benchmark. Validate eventual product decisions against an independently withheld, human-reviewed corpus.
- Tenant/project isolation must be enforced **inside each candidate retrieval API**. Native Codex implementation agents sharing their OS identity does not block this synthetic development exercise.
- No OpenRouter, no external paid provider unless separately approved.
- Native Codex may not expose per-question tokens or tool call telemetry. These fields stay **null**, not zero or guessed. Retrieval can still be evaluated.
- Do not reuse results from the old `bench-0001-cloud-pilot-preflight` branch: it ran no candidate. It is kept solely for historical diagnosis.

See [PROMPT-CODEX-CLOUD.md](PROMPT-CODEX-CLOUD.md), [BENCH-0001.md](BENCH-0001.md) and [WORKER-CONTRACT.md](WORKER-CONTRACT.md).
