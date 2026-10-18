# SOL mission — BENCH-0001 real implementation pilot (Codex Cloud)

Act as the parent SOL coordinator. **Implement and test five candidate memory engines**, not merely another Cloud environment-preflight report.

## Correction to the prior blocked run

The branch `bench-0001-cloud-pilot-preflight` is historical evidence only; DO NOT merge its bulk NOT_RUN records. Its nested `codex exec` isolated through bubblewrap encountered proxy CONNECT 403. This does **not** prove native Codex Luna subagents are unavailable. Sharing an OS UID with the coordinator does NOT prevent native trusted implementation subagents from writing candidate source against a synthetic public corpus.

The synthetic scoring algorithm is already public: do not claim this is a truly blind test. A separate withheld, human-reviewed holdout is required later. The actual security gate is tenant/project isolation **within each candidate's retrieval API**.

## Step 0 — brief environment verification, then code

- Run `bash scripts/cloud-setup.sh`, `python3 -m unittest discover -s tests -v` and `python3 -m benchkit.smoke`.
- Freeze dataset SHA, question IDs, code revision, model alias/effort and prompts.
- Check Python, network/package availability, Docker if needed and native Codex delegation once. Record concise results, not raw dumps.
- Do NOT launch a nested Codex CLI or repeat the failing ChatGPT endpoint probe.
- Native Luna delegates coding work. If five slots unavailable, use waves and record actual concurrency.
- No outside paid provider may be introduced without permission.

## Step 1 — launch implementation workers

Create FIVE Luna workstreams concurrently if available; each has separate write scope and must **deliver functioning code, tests and setup**:

A. Basic Memory: real Markdown ingestion / scoped search, source provenance.
B. Cognee: real graph/vector ingestion and retrieval; document extraction dependencies.
C. Graphiti: real temporal graph backend, revisions and supersession.
D. Qdrant: real hybrid dense/sparse indexed Markdown, tenant filters and source revisions.
E. Direct vault: a native Luna agent given *only scoped filesystem list/read/search* with no RAG index. A deterministic lexical scanner may exist as a labeled smoke control but must NEVER be presented as Luna.

Write code to `implementations/<candidate>/` and evidence to `results/<candidate>/`. Use WORKER-CONTRACT.md. If extraction inference requires an unavailable provider, deliver the adapter and integration path, mark that **stage** blocked, and continue other engines. Never replace source with five READMEs that simply say blocked.

## Step 2 — retrieval pilot FIRST (independent of Luna telemetry)

Run the same 20 frozen questions for each working engine, scoped to authorized org/project, top-k=5. Capture real retrieved document IDs, revisions, scores, latency, CPU/RAM where available, backend calls and file I/O. Try cross-tenant direct API requests. Report failures honestly.

A candidate that cannot run must have one short blocker report with attempted install/start/tests. Continue other candidates rather than stopping everything.

## Step 3 — Luna end-to-end answer pilot IF POSSIBLE

Use native Codex Luna with the same available model/effort and consistent prompts/tools. Avoid answering as SOL pretending to be Luna. If native tools do not support isolated per-question fresh sessions/tool restriction or cannot export exact tool/token counters, mark those measurements N/A and continue valid retrieval tests. Never estimate tokens and call them measured. Do NOT use nested `codex exec` as a workaround.

For completed answer sessions: record actual citations, answer, latency, tools, provider usage if available. Grade only after response traces close; do not look up expected answer generation during responses.

## Step 4 — consolidate, test and STOP

Write tests and run them. Produce `results/COMPARISON.md`, `results/run-manifest.json` and `ADR-0001-memory-benchmark-decision.md` distinguishing IMPLEMENTED, RETRIEVAL_TESTED, ANSWER_TESTED, BLOCKED and NOT_AVAILABLE. Include candidate pinned versions and a reproducibility manifest. Report true token/tool reductions and ingestion amortization only when measurements exist. Keep a separate retrieval-only comparison otherwise.

Do not commit raw environment/auth/proxy dumps, nor hundreds of placeholder rows. Commit candidate source and compact evidence on a Codex feature branch, open a PR.

**STOP after the 20-question pilot.** Do not continue to full corpus or concurrency load until review.

**Definition of done:** actual implementation source and integration tests for at least one candidate, and precise reproducible status for all five. Only capability checks without candidate code = incomplete.
