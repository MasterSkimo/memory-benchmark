# BENCH-0001 — Luna implementation worker contract (Codex Cloud)

Each Luna implements **one candidate** and returns code, integration tests, dependency pins and limitations, not merely a preflight report.

## Isolation of work

Write only to `implementations/<candidate>/` and `results/<candidate>/`. Read shared public inputs (`fixtures/vault`, `fixtures/questions_public.jsonl`, `fixtures/questions_public_pilot.jsonl`, `fixtures/manifest.json`), but never edit them.

Do not inspect or use the public deterministic scorer, gold answers or competitor outputs for constructing answers. Worktrees avoid merge collisions, not malicious cross-agent file reads. True product isolation is a separate backend API test.

## Candidate deliverables

- README with install/start commands and exact SDK/backend/model versions.
- Real adapter/service implementation accepting `question`, `organization_id`, `knowledge_space_id`, `top_k` and returning scoped `hits` with `document_id`, `revision`, `score` and `text`.
- Integration test exercising real backend, authorized scoped query and unauthorized cross-project query.
- Instrumented retrieval traces for **actually executed** questions. Unknown `backend_calls`, `file_reads`, `bytes_read` should be null.
- Manifest listing status, exact dependencies, model/provider IDs if relevant and limitations.
- For Luna direct Markdown, **only a native Luna with file list/read/search counts as end-to-end**; a deterministic scanner is a separate control.

## Lanes

**R — retrieval:** implement and test independently of Luna CLI and per-question tokens. Record top-k hits, latency and provenance. Never expose unauthorized hits.

**E — native Luna end-to-end:** same agent instructions, question order, token/tool limits and model/effort across candidates where supported. Count real tokens/tool calls if available; otherwise N/A. Never silently substitute SOL answers or inferred tokens.

## Blocking rules

No Docker? Try supported host/service setup or explain backend-specific block. Paid model unavailable? Implement code and mark that ingestion stage BLOCKED. Native per-question telemetry unavailable? Continue R lane. Network policy or credentials inaccessible? Do not bypass platform controls.

**Do not generate bulk NOT_RUN placeholders. Stop after 20-question pilot.**
