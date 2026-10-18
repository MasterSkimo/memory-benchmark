# BENCH-0001 — Codex Cloud execution rules

This repository is a research implementation benchmark, not production compliance certification. The corpus is synthetic. **Implement candidates first; never make preflight the whole task.**

1. Read PROMPT-CODEX-CLOUD.md, BENCH-0001.md and WORKER-CONTRACT.md.
2. Use native Codex SOL coordinator and native Luna subagents where available. Do NOT run nested authenticated Codex CLI to test model availability. Failure of a nested endpoint does not block implementation or retrieval tests.
3. Delegate five **real implementation tasks** independently: Basic Memory, Cognee, Graphiti, Qdrant, Luna direct Markdown. Use separate owned directories/worktrees.
4. The deterministic gold generator is public in this repository. This is a transparent development benchmark, **not a secret holdout**. Workers must not consult the gold generator, expected answers or competitors' outputs when constructing answers/retrieval logic. A withheld human-reviewed corpus is needed before product selection.
5. Backend isolation across organizations/projects must be enforced by the retrieval API and tested. OS isolation between trusted synthetic-dataset implementation subagents is NOT a prerequisite for implementation.
6. Record actual model usage and tool events only if exposed. Otherwise use null / NOT_AVAILABLE while proceeding with retrieval quality, citations, backend calls, I/O and latency.
7. No paid external inference without approval, no real client documents, no network-policy bypass or credential copying.
8. Never generate bulk NOT_RUN placeholder traces. One concise blocker record is enough. Include real source and tests for every implementation that can be built.
9. Stop after the 20-question pilot, no full 190-question or load test without review.
10. Commit source, tests and concise redacted evidence; omit secrets, environment dumps and auth traces.
