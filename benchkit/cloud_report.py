"""Freeze public inputs and produce a truthful report for a gated cloud pilot.

This module does not run a candidate, infer answers, generate gold, or invoke the
trusted scorer. NOT_RUN records are a schedule of missing observations, never
successful abstentions. Raw CLI errors remain separate from benchmark metrics.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

CANDIDATES = {
    'basic-memory': 'Basic Memory: Markdown roundtrip, retrieval and MCP',
    'cognee': 'Cognee: graph/vector ingestion and retrieval',
    'graphiti': 'Graphiti: temporal graph and superseded decisions',
    'qdrant-native': 'Qdrant: dense+sparse search, tenant filters and citations',
    'luna-vault-direct': 'Codex Luna: authorized Markdown filesystem reads only',
}
BLOCKERS = ['NATIVE_ISOLATION_NOT_PROVEN', 'ISOLATED_CODEX_ENDPOINT_HTTP_403',
            'PER_QUESTION_TELEMETRY_UNAVAILABLE']


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')


def freeze(root: Path) -> dict:
    """Fail closed if any previously frozen input changed between attempts."""
    public = root / 'fixtures'
    questions = [json.loads(x) for x in
                 (public / 'questions_public_pilot.jsonl').read_text().splitlines()]
    assert len(questions) == 20 and len({q['id'] for q in questions}) == 20
    files = [public / n for n in ('manifest.json', 'questions_public.jsonl',
                                  'questions_public_pilot.jsonl')]
    files += sorted((public / 'vault').rglob('*.md'))
    files += sorted((root / 'config/codex').glob('*'))
    files += [root / n for n in ('AGENTS.md', 'BENCH-0001.md', 'WORKER-CONTRACT.md',
              'PROMPT-CODEX-CLOUD.md', 'pyproject.toml', 'benchkit/cloud_fixtures.py',
              'benchkit/trusted_evaluator.py', 'scripts/cloud-setup.sh')]
    hashes = {str(p.relative_to(root)): digest(p) for p in files}
    snapshot = {
        'benchmark': 'BENCH-0001', 'dataset': json.loads((public / 'manifest.json').read_text()),
        'public_question_ids': [q['id'] for q in questions],
        'pilot_category_counts': dict(Counter(q['id'].split('-')[1] for q in questions)),
        'sha256': hashes,
        'hash_map_sha256': hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(),
        'versions': {'python': '3.12.14', 'codex_cli': '0.159.2', 'docker_server': '28.4.0',
                     'dataset': 'cloud-0.2', 'candidate_engines': {c: None for c in CANDIDATES}},
        'candidate_version_freeze_status': 'INCOMPLETE: no implementation or engine provisioned',
        'model_requested': 'gpt-6-luna', 'model_observed': None,
        'reasoning_effort_requested': 'medium', 'model_snapshot': None,
        'provider': 'built-in Codex/ChatGPT only',
        'oracle_generated': False, 'candidate_execution_started': False,
    }
    path = root / 'results/frozen-inputs.json'
    if path.exists():
        previous = json.loads(path.read_text())
        if previous != snapshot:
            raise ValueError('Frozen inputs changed: create a new declared run instead')
    else:
        write_json(path, snapshot)
    return snapshot


def missing_record(question_id: str, lane: str, condition: str) -> dict:
    """Do not assign zero calls/tokens/latency to a question that never ran."""
    return {
        'question_id': question_id, 'lane': lane, 'cache_condition': condition,
        'status': 'NOT_RUN_BLOCKED', 'blockers': BLOCKERS, 'executed': False,
        'answer': None, 'citations': None, 'hits': None,
        'duration_ms': None, 'recall_at_5': None, 'precision_at_5': None,
        'cross_tenant_safe': None, 'tool_calls': None, 'tool_call_types': None,
        'backend_calls': None, 'llm_calls': None, 'retries': None,
        'file_reads': None, 'bytes_read': None, 'context_bytes': None,
        'usage': {k: None for k in ('input_tokens', 'cached_input_tokens',
                  'output_tokens', 'reasoning_tokens', 'cost_usd')},
        'measurement_source': None,
    }


def report(root: Path) -> None:
    """Require observed denial evidence; never turn a successful run into blocked."""
    results = root / 'results'
    boundary = json.loads((results / 'preflight/isolation.json').read_text())
    stderr = (results / 'preflight/luna-capability.stderr').read_text()
    events = [json.loads(x) for x in
              (results / 'preflight/luna-capability.jsonl').read_text().splitlines()]
    if 'HTTP CONNECT failed with status 403' not in stderr:
        raise ValueError('Expected observed endpoint denial is absent; inspect preflight')
    if any(e.get('type') == 'turn.completed' for e in events):
        raise ValueError('A completed capability turn requires review, not blocked reporting')
    assert boundary['native_same_uid_canary_readable']
    snapshot = freeze(root)
    native = json.loads((results / 'preflight/native-tools.json').read_text())
    runtime = json.loads((results / 'preflight/initial-runtime.json').read_text())
    capabilities = {
        'benchmark': 'BENCH-0001', 'status': 'BLOCKED',
        'observed_at_utc': datetime.now(timezone.utc).isoformat(),
        'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
        'setup': {'command': 'bash scripts/cloud-setup.sh', 'exit_code': 0,
                  'evidence': 'preflight/setup.log'},
        'offline_tests': {'command': 'python3 -m unittest discover -s tests -v',
                          'exit_code': 0, 'tests_passed': 4, 'evidence': 'preflight/tests.log'},
        'runtime_evidence': runtime,
        'network': {'policy': 'restricted', 'policy_observed_state': 'unknown',
                    'package_hosts_observed_reachable': True,
                    'execution_network_permission_required': True,
                    'chatgpt_codex_endpoint': 'HTTP CONNECT 403',
                    'evidence': ['preflight/network.json', 'preflight/network-policy.json',
                                 'preflight/environment-status.json', 'preflight/luna-capability.stderr']},
        'docker': {'available': True, 'client_version': '28.4.0', 'server_version': '28.4.0',
                   'storage_driver': 'vfs', 'initial_images': 0,
                   'evidence': 'preflight/docker.json'},
        'native': native,
        'cli': {'version': '0.159.2', 'exec_json_available': True,
                'normal_home_chatgpt_login': True, 'clean_home_chatgpt_login': False,
                'read_only_managed_auth_selector_login': True,
                'isolated_model_inference': 'BLOCKED_BY_PROXY',
                'requested_model': 'gpt-6-luna', 'verified_served_model': None,
                'requested_effort': 'medium', 'verified_served_effort': None,
                'capability_probe_attempts': 1, 'capability_probe_timeout_seconds': 45,
                'probe_is_benchmark_measurement': False,
                'implicit_chatgpt_mcp_connection_attempts': True,
                'user_configuration_loaded': False,
                'evidence': ['preflight/initial-cli.json', 'preflight/isolation.json',
                             'preflight/luna-capability.jsonl', 'preflight/luna-capability.stderr']},
        'isolation': boundary,
        'counters': {'per_question_tokens_available': False, 'input_tokens': None,
                     'cached_input_tokens': None, 'output_tokens': None,
                     'reasoning_tokens': None, 'cost_usd': None,
                     'native_usage_export_tool_observed': False,
                     'cli_completed_turns': 0, 'subscription_remaining_quota': None,
                     'context_limit_verified': None, 'rate_limit_verified': None},
        'concurrency': {'advertised_native_slots_including_coordinator': 7,
                        'native_workers_launched': 0, 'cli_candidate_workers_launched': 0,
                        'candidate_peak_concurrency': 0, 'candidate_waves': [],
                        'capability_cli_sessions_attempted': 1},
        'blockers': BLOCKERS,
    }
    write_json(results / 'cloud-capabilities.json', capabilities)
    common = {
        'benchmark': 'BENCH-0001', 'status': 'BLOCKED', 'phase': 'pilot-only',
        'frozen_inputs': '../frozen-inputs.json', 'input_hash_map_sha256': snapshot['hash_map_sha256'],
        'pilot_questions_per_candidate': 20, 'cache_conditions': ['cold', 'warm'],
        'planned_question_conditions_per_lane': 40, 'executed_question_conditions_per_lane': 0,
        'requested_model': 'gpt-6-luna', 'requested_reasoning_effort': 'medium',
        'observed_model': None, 'observed_effort': None, 'engine_version': None,
        'implementation_worker_launched': False, 'blockers': BLOCKERS,
        'measured_token_trace_count': 0, 'planned_token_trace_count': 40,
        'planned_token_coverage': 0.0, 'executed_token_coverage': None,
        'measured_tool_trace_count': 0, 'planned_tool_coverage': 0.0,
        'executed_tool_coverage': None, 'scoring_executed': False,
    }
    for candidate, purpose in CANDIDATES.items():
        folder = results / candidate
        write_json(folder / 'manifest.json', dict(common, candidate=candidate, purpose=purpose))
        write_json(folder / 'ingest.json', {
            'candidate': candidate, 'status': 'NOT_RUN_BLOCKED', 'executed': False,
            'elapsed_ms': None, 'bytes_read': None, 'backend_calls': None,
            'llm_extraction': {'calls': None, 'input_tokens': None, 'output_tokens': None, 'failures': None},
            'embeddings': {'calls': None, 'tokens': None, 'failures': None},
            'reranking': {'calls': None, 'tokens': None, 'failures': None},
            'retries': None, 'cost_usd': None, 'blockers': BLOCKERS,
        })
        for filename, lane in [('retrieval.jsonl', 'retrieval'), ('end_to_end.jsonl', 'end_to_end')]:
            records = [missing_record(q, lane, condition)
                       for condition in ('cold', 'warm') for q in snapshot['public_question_ids']]
            (folder / filename).write_text(''.join(json.dumps(r) + '\n' for r in records))
        write_json(folder / 'score.json', {'status': 'NOT_SCORED', 'accuracy': None,
            'recall': None, 'precision': None, 'tenant_leaks': None, 'latency_ms': None,
            'reason': 'No executed observations or isolated evaluator; blocked is not abstention.'})
        write_json(folder / 'events/coordinator-blocker.json', {
            'source': 'coordinator artifact generation, not a worker/provider trace',
            'candidate': candidate, 'event': 'NOT_LAUNCHED', 'blockers': BLOCKERS,
            'raw_capability_events': '../../preflight/luna-capability.jsonl'})
        (folder / 'LIMITATIONS.md').write_text(
            f'# {candidate}: BLOCKED\n\nNo implementation worker, ingestion, retrieval, answer, '
            'tenant-safety test or update test ran. Candidate dependencies and licenses were not '
            'verified or frozen. Docker and package-network access were available, but candidate '
            'services were not provisioned after the shared preflight gates failed.\n\n'
            'Native workers share filesystem read access (non-gold canary read succeeded); '
            'the native spawn schema has no filesystem or tool-scope selector. The controlled '
            'CLI namespace denied tested evaluator paths and supported built-in ChatGPT login, '
            'but its Luna model probe received HTTP CONNECT 403 and timed out after 45 seconds. '
            'No completion, served model ID or token usage was supplied. Implicit ChatGPT MCP '
            'connection attempts also occurred despite a clean home and ignored user config; '
            'a working runner must explicitly constrain tool availability.\n\n'
            'JSONL records are NOT_RUN placeholders for the frozen 20 questions under cold/warm '
            'conditions. Null telemetry is not zero use. They must not be passed to a scorer as '
            'successful abstentions. See ../preflight/ for raw capability evidence.\n')
        implementation = root / 'implementations' / candidate
        implementation.mkdir(parents=True, exist_ok=True)
        (implementation / 'README.md').write_text(
            f'# {purpose}\n\nStatus: **BLOCKED before implementation delegation**.\n\n'
            'No adapter, service deployment, source pin or license assessment is claimed. '
            'See ../../results/' + candidate + '/LIMITATIONS.md and manifest.json.\n\n'
            'Resume only with an oracle-isolated Codex worker runtime, built-in '
            '`gpt-6-luna`/`medium` access, and a verified neutral per-question event collector. '
            'Pin the actual engine source/digests and validate tenant scoping, revision '
            'citations and lifecycle behavior before the frozen pilot. No alternative '
            'provider or deterministic substitute was used.\n')
    write_json(results / 'run-manifest.json', {
        'benchmark': 'BENCH-0001', 'status': 'BLOCKED', 'candidate_ids': list(CANDIDATES),
        'input_hash_map_sha256': snapshot['hash_map_sha256'],
        'base_commit': capabilities['base_commit'],
        'candidate_workers_launched': 0, 'candidate_peak_concurrency': 0,
        'candidate_questions_executed': 0, 'planned_e_question_conditions': 200,
        'verified_e_token_traces': 0, 'planned_token_coverage': 0.0,
        'executed_token_coverage': None, 'r_lane': 'NOT_RUN', 'e_lane': 'NOT_RUN',
        'full_questions': 'NOT_RUN_NOT_AUTHORIZED', 'load_testing': 'NOT_RUN_NOT_AUTHORIZED',
        'mutation_scenarios': 'NOT_RUN', 'oracle_generation': 'NOT_RUN',
        'candidate_version_freeze': 'INCOMPLETE', 'blockers': BLOCKERS,
        'ingest_amortization': {str(n): {c: {'tokens': None, 'cost_usd': None}
                                         for c in CANDIDATES} for n in (20, 200, 2000, 20000)},
        'pareto_frontier': None, 'token_savings_vs_direct': None,
        'call_savings_vs_direct': None,
    })


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path('.'))
    args = parser.parse_args()
    report(args.root.resolve())


if __name__ == '__main__':
    main()
