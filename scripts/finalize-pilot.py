"""Consolidate closed real traces; no candidate or model is executed here."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchkit.evaluate_pilot import evaluate
from benchkit.validate_results import validate


def read(path):
    return json.loads((ROOT / path).read_text())


def write(path, data):
    (ROOT / path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def rows(path):
    return [json.loads(line) for line in (ROOT / path).read_text().splitlines() if line]


def main():
    frozen = read('results/frozen-pilot.json')
    base = Path('results/luna-vault-direct')
    verified = base / 'runs/verified-rerun'
    e_manifest = read(verified / 'manifest.json')
    assert e_manifest['status'] != 'IN_PROGRESS', 'Wait for all native answer sessions to close'
    raw = rows(verified / 'answer-traces.jsonl')
    assert [r['question_id'] for r in raw] == frozen['pilot_ids']
    assert len(raw) == 20
    normalized = []
    for number, source in enumerate(raw, 1):
        row = dict(source)
        question_id = row['question_id']
        events_path = verified / 'events' / f'{question_id}.jsonl'
        events = rows(events_path)
        task = row['native_child_task']
        if not task.startswith('/root/'):
            task = '/root/direct_vault/' + task
        row.update({
            'status': 'ok' if row['status'] in ('ANSWERED', 'ABSTAINED') else row['status'],
            'lane': 'end_to_end', 'native_child_task': task,
            'measurement_source': {'kind': 'native Luna final response and actual filesystem wrapper audit',
                'raw_file': str((verified / 'answer-traces.jsonl').relative_to(base)), 'raw_line': number},
            'served_code_version': e_manifest['served_code_version'],
            'wrapper_event_file': str(events_path.relative_to(base)),
            'duration_ms': None, 'native_tool_calls': None, 'llm_calls': None,
            'backend_calls': None, 'retries': None,
            'wrapper_calls': len(events),
            'file_reads': sum(e['file_reads'] for e in events),
            'bytes_read': sum(e['bytes_read'] for e in events),
            'integrity_guard_file_reads': sum(e['integrity_guard_file_reads'] for e in events),
            'integrity_guard_bytes_scanned': sum(e['integrity_guard_bytes_scanned'] for e in events),
            'wrapper_latency_ms': sum(e['latency_ms'] for e in events),
            'filesystem_operation_latency_ms': sum(e['operation_latency_ms'] for e in events),
            'usage': {k: None for k in ('input_tokens', 'cached_input_tokens', 'output_tokens',
                                      'reasoning_tokens', 'cost_usd')},
        })
        row['file_reads_including_integrity'] = row['file_reads'] + row['integrity_guard_file_reads']
        row['bytes_scanned_including_integrity'] = row['bytes_read'] + row['integrity_guard_bytes_scanned']
        normalized.append(row)
    (ROOT / base / 'end_to_end.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in normalized))
    # The manifest points explicitly at the verified run; old observations remain
    # in their historical directory and are not blended into final scores.
    m = read(base / 'manifest.json')
    m['final_verified_run'] = str(verified.relative_to(base) / 'manifest.json')
    m['canonical_answer_trace'] = 'end_to_end.jsonl'
    m['answer_status'] = 'ANSWER_TESTED_OBSERVATIONAL_20_HASH_VERIFIED_FRESH_SESSIONS'
    m['source_sha256'] = e_manifest['source_sha256']
    m['served_source_sha256'] = e_manifest['source_sha256']
    m['served_code_version'] = e_manifest['served_code_version']
    m['prior_run_qualification'] = 'runs/initial/status.json'
    m['answer_traces'] = 'runs/verified-rerun/answer-traces.jsonl'
    m['wrapper_events'] = 'runs/verified-rerun/events/<question_id>.jsonl'
    m['telemetry']['wrapper_calls'] = sum(r['wrapper_calls'] for r in normalized)
    m['telemetry']['wrapper_file_reads'] = sum(r['file_reads'] for r in normalized)
    m['telemetry']['wrapper_bytes_read'] = sum(r['bytes_read'] for r in normalized)
    write(base / 'manifest.json', m)
    scores = {c: evaluate(c, ROOT) for c in ('basic-memory', 'graphiti', 'qdrant-native', 'luna-vault-direct')}
    summaries = {c: read(f'results/{c}/retrieval-summary.json')
                 for c in ('basic-memory', 'graphiti', 'qdrant-native')}
    # Non-dominance on comparable observed R axes only; no token/native-call axis.
    frontier = []
    for candidate, summary in summaries.items():
        s = scores[candidate]['retrieval']
        vector = (-s['macro_recall_at_5'], -s['macro_precision_at_5'], s['superseded_hits'],
                  summary['latency_ms']['p50'], summary['latency_ms']['p95'])
        dominated = False
        for other, other_summary in summaries.items():
            if other == candidate:
                continue
            o = scores[other]['retrieval']
            alternative = (-o['macro_recall_at_5'], -o['macro_precision_at_5'], o['superseded_hits'],
                           other_summary['latency_ms']['p50'], other_summary['latency_ms']['p95'])
            if all(a <= b for a, b in zip(alternative, vector)) and any(a < b for a, b in zip(alternative, vector)):
                dominated = True
        if not dominated:
            frontier.append(candidate)
    native_totals = {
        'completed_verified_answer_sessions': 20, 'verified_input_token_counters': 0,
        'verified_cached_token_counters': 0, 'verified_output_token_counters': 0,
        'verified_native_tool_counters': 0, 'token_coverage': 0.0,
        'wrapper_calls': sum(r['wrapper_calls'] for r in normalized),
        'source_file_reads': sum(r['file_reads'] for r in normalized),
        'source_bytes_read': sum(r['bytes_read'] for r in normalized),
        'integrity_guard_file_reads': sum(r['integrity_guard_file_reads'] for r in normalized),
        'integrity_guard_bytes_scanned': sum(r['integrity_guard_bytes_scanned'] for r in normalized),
        'native_tool_calls': None, 'input_tokens': None, 'cached_input_tokens': None,
        'output_tokens': None, 'cost_usd': None, 'session_latency_ms': None,
    }
    states = {
        'basic-memory': {'implementation': 'IMPLEMENTED', 'retrieval': 'RETRIEVAL_TESTED',
                         'answer': 'NOT_RUN_COMPARABLE_TOOL_HARNESS_NOT_AVAILABLE', 'mcp': 'BLOCKED_DEPENDENCY_COMPATIBILITY'},
        'cognee': {'implementation': 'ADAPTER_IMPLEMENTED', 'ingestion': 'BLOCKED_TOKENIZER_ASSET_HTTP_403',
                   'retrieval': 'NOT_MEASURED', 'backend_isolation': 'NOT_TESTED',
                   'answer': 'NOT_RUN', 'prior_attempt': 'INVALID_CORPUS_AND_ZERO_SUCCESSFUL_QUERIES'},
        'graphiti': {'implementation': 'IMPLEMENTED_STRUCTURED_EPISODE_VARIANT', 'retrieval': 'RETRIEVAL_TESTED',
                     'semantic_extraction': 'NOT_RUN_NO_PROVIDER', 'answer': 'NOT_RUN_COMPARABLE_TOOL_HARNESS_NOT_AVAILABLE'},
        'qdrant-native': {'implementation': 'IMPLEMENTED_NON_NEURAL_HYBRID', 'retrieval': 'RETRIEVAL_TESTED',
                         'neural_embedding': 'NOT_RUN', 'answer': 'NOT_RUN_COMPARABLE_TOOL_HARNESS_NOT_AVAILABLE'},
        'luna-vault-direct': {'implementation': 'IMPLEMENTED_SCOPED_FILESYSTEM', 'retrieval_control': 'NOT_RUN',
                              'answer': 'ANSWER_TESTED_OBSERVATIONAL', 'strict_native_capability_isolation': 'NOT_AVAILABLE'},
    }
    write('results/run-manifest.json', {
        'benchmark': 'BENCH-0001', 'protocol': '1.1', 'status': 'PILOT_COMPLETE_WITH_STAGE_LIMITATIONS',
        'base_branch': frozen['base_branch'], 'base_commit': frozen['base_commit'],
        'feature_branch': 'codex/bench-0001-real-pilot',
        'scaffold_restored_from': '6e1dcee7a0df53a3511b2efdbcf1ed71adbbd406',
        'fixture_manifest': frozen['fixture_manifest'], 'pilot_ids': frozen['pilot_ids'],
        'states': states, 'native_implementation_workers': 5, 'peak_implementation_concurrency': 5,
        'final_successful_retrieval_queries': 60, 'final_native_answer_sessions': 20,
        'valid_unique_questions_per_candidate': 20, 'final_native_answer_concurrency': 1,
        'retrieval_only_pareto_axes': ['recall@5 up', 'precision@5 up', 'superseded hits down', 'p50 ms down', 'p95 ms down'],
        'retrieval_only_frontier': frontier, 'end_to_end_frontier': None,
        'native_baseline_totals': native_totals,
        'token_savings_vs_direct': None, 'native_tool_savings_vs_direct': None,
        'ingest_token_and_usd_amortization': {str(n): None for n in (20, 200, 2000, 20000)},
        'cache_policy': 'First-scope and reused-adapter queries labelled; physical caches uncontrolled, no true cold-cache claim',
        'corpus_incident': 'corpus-integrity-incident.json',
        'repeat_policy': 'Only same frozen twenty IDs repeated after source security/integrity fixes; prior actual traces retained and qualified',
        'full_read_benchmark': 'NOT_RUN_NOT_AUTHORIZED', 'mutation_scenarios': 'NOT_RUN_NOT_AUTHORIZED',
        'load_tests': 'NOT_RUN_NOT_AUTHORIZED', 'oracle_file_generated': False,
        'external_inference_providers_used': [], 'nested_codex_cli_sessions': 0,
    })
    table = []
    labels = {'basic-memory': 'Basic Memory 0.13.1 / FTS5', 'graphiti': 'Graphiti 0.17.9 / structured Neo4j episodes',
              'qdrant-native': 'Qdrant client 1.15.1 / non-neural hybrid'}
    for candidate, summary in summaries.items():
        r = scores[candidate]['retrieval']
        table.append(f"| {labels[candidate]} | 20/20 | {r['macro_recall_at_5']:.0%} | {r['macro_precision_at_5']:.2%} | "
                     f"{summary['latency_ms']['p50']:.2f} / {summary['latency_ms']['p95']:.2f} | {r['out_of_scope_hits']} / {r['revision_mismatches']} / {r['superseded_hits']} |")
    table_text = '\n'.join(table)
    answer = scores['luna-vault-direct']['answers']
    report = f'''# BENCH-0001 — real implementation pilot

Five native `gpt-6-luna`/medium implementation workers ran concurrently. Three
actual backend variants completed the same twenty-question retrieval pilot;
twenty fresh native Luna sessions completed the direct-filesystem answer pilot.
Cognee has real adapter code but its ingestion remains blocked. No nested Codex
CLI, external inference provider, full benchmark or load test was used.

## P1R — retrieval measurements

| Tested variant | Successful queries | Recall@5 | Precision@5 | p50 / p95 ms | Leaks / revision errors / superseded hits |
|---|---|---|---|---|---|
{table_text}
| Cognee 0.5.1 / Kuzu 0.11.3 / LanceDB 0.40.0 | 0 usable; blocked | N/A | N/A | N/A | NOT_TESTED |
| Luna direct filesystem | No separate deterministic R control | N/A | N/A | N/A | See native E evidence |

Recall and precision cover the 14 support-bearing questions; precision uses a
fixed denominator of five. All 14 had all required sources retrieved. All three
working retrievers also returned nonempty results for all six unsupported or
foreign-scope questions. **Source recall is not answer accuracy or abstention.**
Superseded hits have accurate metadata revisions but contain obsolete facts.

The observed retrieval-only frontier is **{', '.join(frontier)}** on recall,
precision, obsolete-source count and p50/p95 query latency. This describes these
prototype variants in this one pilot; it is not a product/semantic-search winner.
Memory, tokens and native calls are excluded from dominance because comparable
measurements are missing. Basic Memory and Graphiti counters count outer SDK/DB
invocations; hidden driver/internal backend calls are not established by them.

## What actually ran

- Basic Memory: real parser, Markdown SyncService, project-scoped repositories
  and SQLite FTS5; a generic OR-term query adapter. The SDK may edit its input,
  so it receives a validated private copy. Source bytes remain authoritative.
  MCP/CLI startup remains blocked by FastMCP/MCP compatibility; Python SDK R works.
- Graphiti: genuine `EpisodicNode.save` and Graphiti Neo4j driver on pinned Neo4j
  5.26.0. Structured Markdown episodes, current-revision flags and lexical ranking
  are implemented. LLM graph extraction, embedding, Graphiti semantic search and
  temporal inference were not tested. This is not the full Graphiti pipeline.
- Qdrant: genuine embedded Qdrant dense+sparse prefetch and RRF with org AND project
  filters. Dense signed hashing and sparse term counts are non-neural controls,
  not pretrained semantic embeddings. Four scoped adapters each build an index;
  this prototype does not optimize a shared multi-tenant index lifecycle.
- Cognee: pinned real add/cognify/CHUNKS integration code. `add` is blocked before
  storage by a static tiktoken asset HTTP 403. Five checks pass; the actual vector
  retrieval test skips. Successful ingestion, dataset-ID resolution, graph/vector
  retrieval and backend isolation are **unverified**. Local inference is explicitly
  opt-in and loopback-only; no alternative provider was introduced. Its earlier
  twenty failed attempts used a modified corpus and are excluded from comparison.
- Direct vault: no index, embeddings or graph. Native Luna sessions use audited
  scoped list/read/search over Markdown; the lexical filesystem helper alone is
  not presented as Luna. The standalone deterministic R control was not run.

## P1E — native direct-vault answers

| Variant | Fresh verified sessions | Canonical components + exact source citations | Strict string equality | Out-of-scope / wrong-revision citations | Native tokens / full latency |
|---|---|---|---|---|---|
| Luna direct Markdown | {answer['observed_sessions']}/20 | {answer['grounded_component_correct_fraction']:.0%} | {answer['strict_string_match_fraction']:.0%} | {answer['out_of_scope_citations']} / {answer['revision_mismatches']} | NOT_AVAILABLE |
| Other backends | No comparable E harness | N/A | N/A | NOT_TESTED | NOT_AVAILABLE |

Component scoring is the declared deterministic canonical-value containment plus
all required exact-revision citations; it is not human semantic evaluation.
All unsupported/unauthorized baseline questions abstained. Responses were graded
only after sessions closed. Native runtime cannot enforce a restricted capability
set or export exact tokens/tool counters/full wall time here. The E observations
use prompt binding and actual wrapper audit; they do not establish strict tool
parity or hostile-shell authorization. API tests enforce scope for a bound
principal instance; a production service must bind that principal outside model
control. Backend answer pilots were not substituted with SOL or lexical answers.

Token coverage is **0/{answer['observed_sessions']}** completed verified answers.
Input/cached/output/reasoning tokens, actual USD, model requests, retries, native
tool counts and full-session latency remain null. The model alias/effort selected
by native delegation is recorded; immutable served snapshots and coordinator
SOL/high identity are not independently exported. Wrapper calls are a separate
instrumented layer: {native_totals['wrapper_calls']} successful file-tool operations,
{native_totals['source_file_reads']:,} source reads and {native_totals['source_bytes_read']:,} UTF-8 bytes.
Integrity guards additionally scanned {native_totals['integrity_guard_file_reads']:,} files /
{native_totals['integrity_guard_bytes_scanned']:,} bytes. These costs are recorded separately,
and must be included when assessing total benchmark I/O. The guard computes a
trusted corpus digest; it returns no cross-tenant source content to Luna.
Wrapper/operation durations are not native end-to-end latency.

## Ingestion, caching and cost

Per-scope factory setup and known ingestion I/O are in each `ingest.json` and
`retrieval-summary.json`. Factory timing includes initialization/validation/sync,
not solely indexing. Qdrant/Graphiti each read the 1,000-file corpus per factory;
Basic Memory's internal sync I/O is not exported. The tested variants do not
invoke extraction/embedding/rerank models; Cognee stops before those stages.
No reported provider token/cost events exist for index or answer consumption.

| Workload queries N | Token savings vs direct | Native-call savings | Ingest + answer tokens/USD amortized |
|---|---|---|---|
| 20 | N/A | N/A | N/A |
| 200 | N/A | N/A | N/A |
| 2,000 | N/A | N/A | N/A |
| 20,000 | N/A | N/A | N/A |

The future formula is ingest usage/N plus per-answer input+output; cached input
and reasoning are overlapping breakdowns. No zero or text-length proxy replaces
missing usage. First-scope vs reused-adapter query groups are separate in the
summaries; OS caches are uncontrolled, so these are not true cold/warm-cache
experiments. Setup and integrity-check I/O are excluded from query durations and
identified separately. Process CPU/RSS is captured where available; Neo4j server
memory/CPU and physical disk I/O are not included in its Python process counters.
Implementations/other workstreams shared resources, so timings are descriptive,
without confidence intervals or throughput claims.

## Integrity, source and reproducibility

The requested corrective branch accidentally removed setup/generator/tests; those
were restored from its parent `6e1dcee`. The same public seed42/cloud-0.2 corpus,
questions, policy and limits were frozen before workers. The corpus digest is
`644b954c4ffe3dbe255e03fe3c24eb9e7bf7248db3790edfeba3ae2bc311e716`.

An initial Basic Memory sync added permalink metadata to 400 shared notes.
That run is invalid. Cognee's failed attempt and the initial direct observations
are also explicitly qualified, rather than blended into final measurements.
The corpus was restored, Basic Memory changed to private-copy sync, and final R
pilots verify hashes before setup, after every factory and after execution. Final
native E tools verify the exact hash before/after every operation. Only the same
twenty IDs were repeated after these fixes; all earlier actual traces remain
under qualified `runs/` directories. See `corpus-integrity-incident.json`.

Real integration tests cover org/project request tampering, shared-backend foreign
sources, exact revision updates and forged provenance; direct tools additionally
test path traversal/symlinks/call budgets/integrity failures. Cognee's backend
isolation is not proven while storage is blocked. No secret holdout is claimed:
the scorer/generator are public, the pilot uses four alpha projects and only the
first variant of each category, and synthetic answers repeat. A withheld,
human-reviewed corpus and comparable embedding/extraction configuration are
required before a product decision.

Reproduction: candidate READMEs and pinned locks, `results/frozen-pilot.json`,
`results/run-manifest.json`, real JSONL/events, `results/reproducibility.json`.
Run `python3 -m unittest discover -s tests -v` and
`python3 -m benchkit.validate_results`; final consolidation is
`python3 scripts/finalize-pilot.py` after actual candidate traces close. No full
190-question, mutation or load phase is authorized or executed.
'''
    (ROOT / 'results/COMPARISON.md').write_text(report)
    adr = f'''# ADR-0001 — Preserve Markdown ownership and a scoped retrieval boundary

Date: 2026-10-18. Status: **Pilot decision; product engine selection deferred**.

Keep project Markdown/Git as authoritative knowledge. Place a narrow read API in
front of rebuildable indexes, bind organization/project from trusted caller
authorization, and return document ID plus exact revision. SDKs that mutate
Markdown must ingest private working copies. Verify corpus integrity around
ingestion and keep native answers separate from retriever metrics.

This decision is backed by actual code/tests and three verified twenty-query
pilots: Basic Memory FTS5 ({summaries['basic-memory']['latency_ms']['p50']:.2f} ms p50),
structured Graphiti/Neo4j episodes ({summaries['graphiti']['latency_ms']['p50']:.2f} ms), and
non-neural Qdrant hybrid ({summaries['qdrant-native']['latency_ms']['p50']:.2f} ms).
Each retrieved all required sources on the fourteen support-bearing questions,
with zero observed out-of-scope hits or revision mismatches. Graphiti suppressed
all obsolete notes; Basic Memory and Qdrant returned three superseded hits each.
All three returned results on unsupported/foreign questions, so retrieval alone
does not establish safe answer abstention. The observed R-only frontier is
{', '.join(frontier)}; it cannot rank the full semantic products.

Twenty fresh native Luna direct-file sessions produced
{answer['grounded_component_correct_fraction']:.0%} grounded canonical-component matches and
{answer['strict_string_match_fraction']:.0%} strict string matches, with correct abstention and
no observed wrong-scope/revision citations. Native capability restriction and
per-question tokens/native calls/full latency are unavailable; these are
observational answers, not a complete comparable E benchmark. Token savings,
native-call savings, monetary costs and 20/200/2k/20k usage amortization remain N/A.

Basic Memory MCP startup is separately blocked by package compatibility. Cognee
has an adapter and five passing checks, but tokenizer HTTP403 blocks ingestion;
its real retrieval test skips and backend isolation/provenance are unverified.
Graphiti uses structured episodes/custom lexical ranking without graph extraction
or temporal inference; Qdrant uses explicit local hashing rather than neural
embeddings. These choices avoid paid providers but limit product comparisons.

An initial SDK sync modified shared metadata. The public corpus was restored,
the writing SDK now receives a private copy, and final traces have hash guards.
Earlier runs are preserved and qualified. This incident is implementation
evidence for the ownership boundary, not a retrieval-quality result.

Do not select a final vendor from this small, public, repeated-answer synthetic
pilot. After review, validate comparable local semantic/extraction models, repair
the blocked MCP/Cognee stages, expose authenticated scoped read services, and
evaluate a withheld human-reviewed corpus. This run stops at the frozen twenty
questions; full/read mutation and concurrent-load phases still require review.

Evidence: [comparison](results/COMPARISON.md), [manifest](results/run-manifest.json),
[integrity incident](results/corpus-integrity-incident.json),
[frozen inputs](results/frozen-pilot.json), and each candidate's source/tests/events.
'''
    (ROOT / 'ADR-0001-memory-benchmark-decision.md').write_text(adr)
    validate(ROOT)
    # Seal actual source and compact evidence, omitting package trees/runtime DBs.
    paths = []
    for directory in ('benchkit', 'scripts', 'tests', 'config', 'implementations'):
        for path in (ROOT / directory).rglob('*'):
            if path.is_file() and not any(part in ('.venv', '__pycache__', '.state', 'runtime-home') for part in path.parts):
                if path.suffix in ('.py', '.md', '.txt', '.json', '.sh', '.toml', '.lock') or path.name in ('requirements.lock', '.gitignore'):
                    paths.append(path)
    paths += [p for p in (ROOT / 'results').rglob('*') if p.is_file() and p.name != 'reproducibility.json']
    write('results/reproducibility.json', {
        'benchmark': 'BENCH-0001', 'corpus_sha256': frozen['fixture_manifest']['vault_sha256'],
        'file_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(paths))},
        'note': 'Candidate package/backend versions are pinned in their manifests/locks; native immutable model IDs and usage are not exported.'})
    print('Final comparison, ADR, manifests and evidence hashes written')


if __name__ == '__main__':
    main()
