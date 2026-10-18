# BENCH-0001 — pilot BLOCKED

No candidate implementation worker or benchmark question ran. No candidate wins,
Pareto frontier, token savings, call savings, correctness, safety or latency can be
reported. All five arms are **BLOCKED**, with incomplete engine version freezes.
The one attempted CLI session was a capability probe, not an answer or retrieval
measurement. The experiment stopped before pilot execution; full questions,
mutation and concurrent-load phases were not run.

## Observed capabilities

- `bash scripts/cloud-setup.sh` succeeded: Python 3.12.14, 1,000 public notes,
  200 public questions, 20 pilot questions, seed 42, dataset `cloud-0.2`.
  The separately requested unittest command passed all four original tests.
- Docker client/server 28.4.0 is usable through the local socket with network
  permission. Storage driver: `vfs`; initially zero images and containers.
  Default-sandbox `EPERM` was resolved with supported execution permissions.
  No daemon restart, image pull or candidate deployment occurred.
- Package hosts PyPI and GitHub returned HTTP 200 through the configured proxy.
  The environment reports restricted networking and policy observation `unknown`;
  host reachability is observed, not a claim of universal connectivity.
- Codex CLI 0.159.2 has `exec --json`. Normal runtime login reports ChatGPT.
  An empty isolated Codex home is not logged in; selecting the existing managed
  auth file read-only inside bubblewrap reports ChatGPT login. Credentials were
  not inspected, copied, logged, committed or put in Docker.
- Native `collaboration.spawn_agent` advertises `gpt-6-luna`, including medium
  effort, and seven slots including the coordinator. It has no filesystem,
  process-identity or tool-scope selector and no usage export in its result schema.
  Coordinator SOL/high was requested, but the served coordinator ID/effort and
  immutable model snapshots are not exposed and remain null. No provider was substituted.

## Blocking evidence

1. **Native isolation not proven.** A same-UID child successfully read a non-gold
   evaluator canary. Native agents share filesystem access; a worktree or fresh
   context would not deny reads. No native worker was spawned.
2. **Controlled CLI endpoint denied.** A bubblewrap namespace could read its
   allowed fixture while denying the outside canary, repository, grader, potential
   oracle path, Docker socket and `/proc/1/root` route. It mounted no gold or grader.
   After this check, one CLI probe requested `gpt-6-luna`/`medium` and the literal
   response `CAPABILITY_OK`, with no requested tools. Proxy HTTP CONNECT 403 blocked
   `wss://chatgpt.com/backend-api/codex/responses`; HTTPS fallback also failed.
   The probe timed out after 45 seconds without a completed turn or usage event.
   Authentication readiness therefore did not establish inference access.
3. **Telemetry unavailable.** Native tools offer no observed per-question usage
   export; the isolated CLI supplied errors but no completion/token counters.
   The served Luna model/effort was not verified. Implicit ChatGPT MCP connection
   attempts also appeared despite clean user configuration; any resumed runner
   must verify explicit tool restriction. No MCP result or candidate data was sent.

Raw evidence: [capabilities](cloud-capabilities.json),
[isolation probe](preflight/isolation.json), [CLI events](preflight/luna-capability.jsonl),
[CLI stderr](preflight/luna-capability.stderr), [Docker](preflight/docker.json),
[network probes](preflight/network.json), [setup](preflight/setup.log),
[offline tests](preflight/tests.log). Probe timing is not candidate latency.

## Candidate outcomes

| Candidate | Implementation / ingest | R lane | E lane | Safety / revisions | Tokens / calls / latency |
|---|---|---|---|---|---|
| Basic Memory | BLOCKED | NOT_RUN | NOT_RUN | NOT_TESTED | N/A |
| Cognee | BLOCKED | NOT_RUN | NOT_RUN | NOT_TESTED | N/A |
| Graphiti | BLOCKED | NOT_RUN | NOT_RUN | NOT_TESTED | N/A |
| Qdrant hybrid | BLOCKED | NOT_RUN | NOT_RUN | NOT_TESTED | N/A |
| Luna direct Markdown | BLOCKED | NOT_RUN | NOT_RUN | NOT_TESTED | N/A |

Candidate services were not provisioned after the shared preflight failure;
this does not establish that those engines are unavailable or defective. Their
source pins, dependency versions and licenses remain unverified. No deterministic
retriever replaced Luna, and no hidden paid provider, embedding model, extraction
model or reranker was used. Actual unreported provider usage/cost remains unknown.

Each arm contains 40 **NOT_RUN placeholders per lane**: the same frozen 20 question
IDs under separately labelled cold/warm conditions. These are scheduled missing
observations, not raw worker traces, measured failures, successful abstentions or
zero-use answers. Each telemetry field is null. Candidate event files explicitly
identify themselves as coordinator blocker records.

Coverage: **0/200 planned E question/condition observations** have verified token
or tool counters (0% planned coverage). Coverage among executed observations is
N/A because the denominator is zero. There were zero candidate workers, zero
waves and zero candidate concurrency. A separate capability CLI session was
attempted once. Raw reconnect messages do not establish request/token counts.

## Pareto comparison and amortization

The frontier is **undefined**: no arm has measured quality, security, tokens,
calls or latency. Savings against direct vault Luna are N/A for every arm because
the direct baseline did not run. Do not interpret blocked arms as tied winners.

| Candidate | 20 queries | 200 queries | 2,000 queries | 20,000 queries |
|---|---|---|---|---|
| Basic Memory | N/A | N/A | N/A | N/A |
| Cognee | N/A | N/A | N/A | N/A |
| Graphiti | N/A | N/A | N/A | N/A |
| Qdrant hybrid | N/A | N/A | N/A | N/A |
| Luna direct Markdown | N/A | N/A | N/A | N/A |

These cells require separately measured ingestion extraction/embedding/rerank
usage and per-answer usage. The declared future calculation is
`ingest_tokens / N + answer_input_tokens + answer_output_tokens`; cached input
and reasoning are subsets, not extra raw tokens. Monetary amortization requires
reported cost and also remains N/A. Failure/retry costs must be included.

## Frozen inputs and limits

[frozen-inputs.json](frozen-inputs.json) lists all public file SHA-256 digests,
question order, protocol, prompts and planned budgets. The vault digest is
`644b954c4ffe3dbe255e03fe3c24eb9e7bf7248db3790edfeba3ae2bc311e716`.
Candidate version/model snapshot freezing is explicitly incomplete. The model
sampling seed, temperature and verified context/rate/subscription limits are unknown;
the fixture seed is 42. Planned token/call budgets were not enforced or consumed
by a candidate runner. The capability probe had its own 45-second timeout.

The existing scorer was not invoked: absent/blocked records must never count as
successful negative-question abstentions. No gold file was generated; a resumed
run needs a separate trusted evaluator after closing actual candidate traces.
Synthetic data, four-project pilot coverage and no human holdout further limit
any future recommendation. Corpus, questions and grader were not changed.

To resume, supply an enforced oracle-isolated native worker runtime or enable the
supported isolated built-in Codex endpoint through the environment configuration
workflow. Then verify tool parity/usage, pin engines, and run only the frozen
pilot. Broader testing still requires review. Do not bypass the proxy or switch
providers to work around the denial.
