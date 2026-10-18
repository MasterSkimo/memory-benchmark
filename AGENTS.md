# Benchmark-only repository instructions

This is a scientific **Codex Cloud** evaluation, not production application code.

- Follow BENCH-0001.md, WORKER-CONTRACT.md and PROMPT-CODEX-CLOUD.md.
- Test with the same Codex Luna model/effort wherever the service actually exposes them; record model identifiers and versions. Do not invent immutable snapshot names.
- Do not use OpenRouter, developer API keys or surprise paid inference services. Ask for approval if an external ingestion model is required.
- Keep the evaluator answer oracle OUTSIDE the agent's filesystem and prompts. If no real isolation is available, mark ISOLATION_NOT_PROVEN.
- Five independent candidate implementations, same public corpus, pilot first; coordinator integrates evidence and reports.
- Preserve source revisions, benchmark manifests, tokens, tool calls, backend calls and failures. Never invent telemetry.
- Do not run full 190-question or concurrent load testing before review of pilot.
- Do not alter frozen questions or score criteria to improve results.
- Include code comments and run integration tests.
