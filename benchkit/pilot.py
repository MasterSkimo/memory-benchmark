"""Neutral retrieval pilot: twenty frozen public questions, no gold imports.

Run this module with the candidate's pinned Python environment. The candidate
factory fixes authorization at construction; changing question scope is forbidden.
Actual traces close before any separate evaluation step.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import resource
import statistics
import sys
import time
import traceback


def load_adapter(path: Path):
    spec = importlib.util.spec_from_file_location('candidate_adapter', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    spec.loader.exec_module(module)
    return module


def percentile(values, fraction):
    if not values:
        return None
    values = sorted(values)
    position = (len(values) - 1) * fraction
    low = int(position)
    high = min(low + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (position - low)


def vault_digest(corpus: Path) -> str:
    """Use the frozen generator's public content digest, without importing it."""
    content = '\n'.join(path.read_text(encoding='utf-8')
                        for path in sorted(corpus.rglob('*.md')))
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def execute(candidate: str, adapter_path: Path, corpus: Path, questions_path: Path,
            output: Path, frozen_path: Path) -> dict:
    frozen = json.loads(frozen_path.read_text())
    questions = [json.loads(line) for line in questions_path.read_text().splitlines() if line]
    if len(questions) != 20 or [q['id'] for q in questions] != frozen['pilot_ids']:
        raise ValueError('Only the exact frozen twenty-question pilot is authorized')
    expected_hash = frozen['file_sha256']['fixtures/questions_public_pilot.jsonl']
    if hashlib.sha256(questions_path.read_bytes()).hexdigest() != expected_hash:
        raise ValueError('Public pilot hash changed')
    expected_corpus = frozen['fixture_manifest']['vault_sha256']
    if vault_digest(corpus) != expected_corpus:
        raise ValueError('Frozen corpus hash changed before candidate execution')
    module = load_adapter(adapter_path)
    output.mkdir(parents=True, exist_ok=True)
    adapters = {}
    setups = []
    records = []
    abort = False
    with (output / 'retrieval.jsonl').open('w') as stream:
        for question in questions:
            scope = (question['organization_id'], question['knowledge_space_id'])
            is_new = scope not in adapters
            if is_new:
                started = time.perf_counter()
                adapters[scope] = module.create_adapter(corpus, *scope)
                if vault_digest(corpus) != expected_corpus:
                    raise ValueError('Candidate setup modified the frozen public corpus')
                setup = {'organization_id': scope[0], 'knowledge_space_id': scope[1],
                         'factory_elapsed_ms': (time.perf_counter() - started) * 1000}
                for name in ('ingest_file_reads', 'ingest_bytes_read', 'ingest_backend_calls',
                             'ingest_embedding_calls'):
                    setup[name] = getattr(adapters[scope], name, None)
                setups.append(setup)
            adapter = adapters[scope]
            before = resource.getrusage(resource.RUSAGE_SELF)
            started = time.perf_counter()
            row = {'candidate': candidate, 'question_id': question['id'], 'lane': 'retrieval',
                   'organization_id': scope[0], 'knowledge_space_id': scope[1],
                   'top_k': 5, 'cache_condition': 'first_scope_query' if is_new else 'reused_scope_adapter',
                   'physical_cache_state': 'UNCONTROLLED', 'input_tokens': None,
                   'cached_input_tokens': None, 'output_tokens': None, 'native_tool_calls': None}
            try:
                result = adapter.search(question, top_k=5)
                hits = result['hits']
                if len(hits) > 5:
                    raise ValueError('Adapter exceeded top_k=5')
                prefix = '/'.join(scope) + '/'
                for hit in hits:
                    if not hit.get('revision') or not isinstance(hit.get('text'), str):
                        raise ValueError('Missing exact source provenance/text')
                    if not str(hit.get('document_id', '')).startswith(prefix):
                        abort = True
                        raise PermissionError('TENANT_LEAK: returned document outside authorization')
                row.update({'status': 'ok', 'hits': hits,
                            'backend_calls': result.get('backend_calls'),
                            'file_reads': result.get('file_reads'), 'bytes_read': result.get('bytes_read'),
                            'embedding_calls': result.get('embedding_calls'),
                            'rerank_calls': result.get('rerank_calls'),
                            'adapter_tool_calls': result.get('tool_calls')})
            except Exception as error:
                row.update({'status': 'tenant_leak' if abort else 'error',
                            'error_type': type(error).__name__, 'error': str(error), 'hits': None,
                            'backend_calls': None, 'file_reads': None, 'bytes_read': None})
            after = resource.getrusage(resource.RUSAGE_SELF)
            row.update({'duration_ms': (time.perf_counter() - started) * 1000,
                        'cpu_user_seconds': after.ru_utime - before.ru_utime,
                        'cpu_system_seconds': after.ru_stime - before.ru_stime,
                        'process_peak_rss_kib': after.ru_maxrss})
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
            stream.flush()
            records.append(row)
            if abort:
                break
    for adapter in adapters.values():
        if hasattr(adapter, 'close'):
            adapter.close()
    if vault_digest(corpus) != expected_corpus:
        raise ValueError('Frozen corpus changed during pilot; traces are invalid')
    durations = [r['duration_ms'] for r in records if r['status'] == 'ok']
    summary = {'candidate': candidate, 'status': 'TENANT_LEAK_ABORT' if abort else
               ('RETRIEVAL_TESTED' if len(durations) == 20 else 'INCOMPLETE'),
               'questions_executed': len(records), 'successful_queries': len(durations),
               'status_counts': dict(Counter(r['status'] for r in records)),
               'latency_ms': {'p50': percentile(durations, .5), 'p95': percentile(durations, .95)},
               'cache_groups': {condition: {'queries': sum(r['cache_condition'] == condition for r in records),
                   'p50_ms': percentile([r['duration_ms'] for r in records if r['status'] == 'ok'
                                        and r['cache_condition'] == condition], .5)}
                   for condition in ('first_scope_query', 'reused_scope_adapter')},
               'setups': setups, 'setup_excluded_from_query_latency': True,
               'process_peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
               'native_token_coverage': 0, 'native_token_counter_source': 'NOT_AVAILABLE',
               'questions_sha256': expected_hash,
               'corpus_sha256': expected_corpus, 'corpus_integrity': 'VERIFIED_BEFORE_SETUP_AFTER_EACH_FACTORY_AND_AFTER_RUN',
               'integrity_check_io_excluded_from_query_metrics': True,
               'adapter_sha256': hashlib.sha256(adapter_path.read_bytes()).hexdigest(),
               'scoring': 'NOT_RUN: traces must close before separate evaluation'}
    (output / 'retrieval-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--adapter', type=Path, required=True)
    parser.add_argument('--corpus', type=Path, default=Path('fixtures/vault'))
    parser.add_argument('--questions', type=Path, default=Path('fixtures/questions_public_pilot.jsonl'))
    parser.add_argument('--frozen', type=Path, default=Path('results/frozen-pilot.json'))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(execute(args.candidate, args.adapter.resolve(), args.corpus.resolve(),
                             args.questions.resolve(), args.out, args.frozen), indent=2))


if __name__ == '__main__':
    main()
