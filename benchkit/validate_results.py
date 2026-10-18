"""Verify final pilot evidence, source provenance and actual corpus integrity."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from benchkit.evaluate_pilot import source_catalog
from benchkit.pilot import vault_digest


def records(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def validate(root: Path):
    frozen = json.loads((root / 'results/frozen-pilot.json').read_text())
    ids = frozen['pilot_ids']
    expected = frozen['fixture_manifest']['vault_sha256']
    assert vault_digest(root / 'fixtures/vault') == expected
    for name, digest in frozen['file_sha256'].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest, name
    catalog = source_catalog(root / 'fixtures/vault')
    for candidate in ('basic-memory', 'graphiti', 'qdrant-native'):
        folder = root / 'results' / candidate
        rows = records(folder / 'retrieval.jsonl')
        assert [r['question_id'] for r in rows] == ids
        summary = json.loads((folder / 'retrieval-summary.json').read_text())
        assert summary['successful_queries'] == 20
        assert summary['corpus_sha256'] == expected
        assert summary['corpus_integrity'].startswith('VERIFIED_')
        assert hashlib.sha256((root / 'implementations' / candidate / 'adapter.py').read_bytes()).hexdigest() == summary['adapter_sha256']
        for row in rows:
            assert row['status'] == 'ok'
            prefix = row['organization_id'] + '/' + row['knowledge_space_id'] + '/'
            assert len(row['hits']) <= 5
            for hit in row['hits']:
                assert hit['document_id'].startswith(prefix)
                assert hit['revision'] == catalog[hit['document_id']]['revision']
    direct = root / 'results/luna-vault-direct'
    rows = records(direct / 'end_to_end.jsonl')
    questions = {q['id']: q for q in records(root / 'fixtures/questions_public_pilot.jsonl')}
    assert [r['question_id'] for r in rows] == ids
    assert len({r['native_child_task'] for r in rows}) == 20
    for row in rows:
        assert row['status'] == 'ok' and row['fork_turns'] == 'none'
        assert row['model'] == 'gpt-6-luna' and row['effort'] == 'medium'
        assert all(value is None for value in row['usage'].values())
        event_path = direct / row['wrapper_event_file']
        q = questions[row['question_id']]
        prefix = q['organization_id'] + '/' + q['knowledge_space_id'] + '/'
        raw_path = direct / row['measurement_source']['raw_file']
        raw_row = records(raw_path)[row['measurement_source']['raw_line'] - 1]
        assert raw_row['answer'] == row['answer'] and raw_row['citations'] == row['citations']
        events = records(event_path)
        assert 1 <= len(events) <= 12
        for event in events:
            assert event['question_id'] == row['question_id']
            assert all(source_id.startswith(prefix) for source_id in event['source_ids'])
            assert event['status'] == 'OK'
            assert event['pristine_verified'] is True
            assert event['frozen_vault_sha256_before'] == expected
            assert event['frozen_vault_sha256_after'] == expected
            assert event['timestamp_utc']
        for citation in row['citations']:
            assert citation['document_id'].startswith(prefix)
            assert citation['revision'] == catalog[citation['document_id']]['revision']
    manifest = json.loads((direct / 'runs/verified-rerun/manifest.json').read_text())
    assert manifest['status'] != 'IN_PROGRESS'
    for name, digest in manifest['source_sha256'].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest, name
    cognee = json.loads((root / 'results/cognee/manifest.json').read_text())
    assert cognee['pilot']['status'] == 'INVALID_FOR_COMPARATIVE_RETRIEVAL'
    assert cognee['integration_tests']['skipped'] == 1
    assert not (root / 'fixtures/private').exists()
    print('PASS: frozen corpus/policies; 60 verified R queries; 20 fresh native E responses and hashed wrapper events; provenance; blocked Cognee qualified; no oracle')


if __name__ == '__main__':
    validate(Path('.').resolve())
