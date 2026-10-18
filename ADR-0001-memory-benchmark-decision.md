# ADR-0001 — Defer memory-engine selection: pilot blocked

Date: 2026-10-18. Status: **Deferred pending valid pilot evidence**.

BENCH-0001 asks which project-owned memory approach gives grounded, cited answers
with the lowest token and tool-call use under enforced tenant isolation. This run
does not select Basic Memory, Cognee, Graphiti, Qdrant or direct Markdown Luna.
No candidate implementation, ingestion, retrieval or end-to-end question ran.

Offline setup and four original tests passed. Python 3.12.14, Codex CLI 0.159.2,
Docker 28.4.0 and package-network access were observed. The native delegation tool
advertises `gpt-6-luna`/medium and seven total slots, but exposes no filesystem
isolation control or usage export. A same-UID canary read confirmed shared read
access. No native implementation worker was launched.

A controlled bubblewrap namespace denied tested evaluator, grader and host paths
before any model invocation. It used a clean Codex home and a read-only selector
for existing managed ChatGPT authentication; no credential bytes were inspected
or copied. The one isolated Luna capability probe received proxy CONNECT 403
for the built-in Codex endpoint and timed out after 45 seconds. There was no
completed turn, served model confirmation or token accounting. Implicit ChatGPT
MCP connection attempts also require tool-policy verification before resuming.
The coordinator's exact served SOL/high identity could not be independently
confirmed. No alternate provider was used.

The decision is to **defer the architecture choice** and preserve the frozen
public pilot and raw preflight evidence. All five arms are BLOCKED; unknown
tokens, cost, calls, correctness, safety and latency are null. Planned token/tool
coverage is 0/200 cold/warm question observations; coverage among executed
observations is undefined. Pareto ranking, baseline savings and ingestion
amortization at 20/200/2,000/20,000 queries are unavailable. Engine versions and
licenses remain unverified because no services were provisioned.

Resumption requires a supported oracle-isolated worker boundary and reachable
built-in Codex subscription endpoint, plus verified per-question traces and
explicit read-only tool policy. Pin engine sources and dependencies before
ingestion. Keep the same fresh Luna/medium model, prompts, public question order
and tool budgets across candidates. Generate and score gold only in a separate
trusted evaluator after candidate traces close. Preserve ingestion extraction,
embedding, rerank, retry and failure usage separately.

Do not run full questions, mutation scenarios or concurrent-load phases until
the pilot has been reviewed. The existing corpus and grader remain unchanged.
No vendor can be preferred from this capability-only evidence. Synthetic fixture
results would still require later confirmation on an authorized human-reviewed
holdout corpus.

Evidence and reproducibility: [comparison](results/COMPARISON.md),
[capabilities](results/cloud-capabilities.json),
[run manifest](results/run-manifest.json),
[frozen public hashes](results/frozen-inputs.json), and
[raw CLI events](results/preflight/luna-capability.jsonl).

Validate the saved run with `python3 scripts/validate-cloud-results.py` and
`python3 -m unittest discover -s tests -v`. These checks validate artifacts and
offline behavior; they do not turn this blocked pilot into benchmark measurements.
