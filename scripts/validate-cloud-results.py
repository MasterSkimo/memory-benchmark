"""Integration checks for this blocked pilot's evidence and frozen artifacts."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from benchkit.cloud_report import CANDIDATES, freeze

results = root / 'results'
frozen = freeze(root)
for relative, expected in frozen['sha256'].items():
    assert hashlib.sha256((root / relative).read_bytes()).hexdigest() == expected, relative
capabilities = json.loads((results / 'cloud-capabilities.json').read_text())
assert capabilities['docker']['available']
assert capabilities['cli']['verified_served_model'] is None
assert capabilities['isolation']['namespace_probe_exit_code'] == 0
assert capabilities['isolation']['native_same_uid_canary_readable'] is True
assert not capabilities['isolation']['oracle_generated']
assert not (root / 'fixtures/private').exists()
assert 'HTTP CONNECT failed with status 403' in (results / 'preflight/luna-capability.stderr').read_text()
raw = [json.loads(line) for line in (results / 'preflight/luna-capability.jsonl').read_text().splitlines()]
assert any(e['type'] == 'turn.started' for e in raw)
assert not any(e['type'] == 'turn.completed' for e in raw)
for candidate in CANDIDATES:
    folder = results / candidate
    manifest = json.loads((folder / 'manifest.json').read_text())
    assert manifest['status'] == 'BLOCKED'
    assert not manifest['implementation_worker_launched']
    assert manifest['planned_token_coverage'] == 0
    assert manifest['executed_token_coverage'] is None
    for filename in ('retrieval.jsonl', 'end_to_end.jsonl'):
        records = [json.loads(x) for x in (folder / filename).read_text().splitlines()]
        assert len(records) == 40
        for condition in ('cold', 'warm'):
            subset = [r for r in records if r['cache_condition'] == condition]
            assert [r['question_id'] for r in subset] == frozen['public_question_ids']
        for row in records:
            assert row['status'] == 'NOT_RUN_BLOCKED' and row['executed'] is False
            assert all(value is None for value in row['usage'].values())
            assert row['tool_calls'] is None and row['duration_ms'] is None
            assert row['citations'] is None and row['hits'] is None
    assert json.loads((folder / 'score.json').read_text())['accuracy'] is None
subprocess.run(['git', 'diff', '--exit-code', '--', 'benchkit/cloud_fixtures.py',
                'benchkit/trusted_evaluator.py', 'tests/test_cloud.py',
                'tests/test_evaluator.py'], cwd=root, check=True)
print('PASS: frozen public hashes, 5 blocked arms, 400 NOT_RUN lane records, null telemetry, raw endpoint denial, unchanged corpus/grader')
