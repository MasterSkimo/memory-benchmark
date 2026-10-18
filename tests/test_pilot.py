"""The neutral runner must stop on a leak and reject non-frozen questions."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from benchkit.pilot import execute


class PilotBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.questions = self.root / 'questions.jsonl'
        rows = [{'id': f'test-{i}', 'organization_id': 'a',
                 'knowledge_space_id': 'p', 'question': 'test'} for i in range(20)]
        self.questions.write_text(''.join(json.dumps(row) + '\n' for row in rows))
        self.frozen = self.root / 'frozen.json'
        self.frozen.write_text(json.dumps({'pilot_ids': [r['id'] for r in rows],
            'fixture_manifest': {'vault_sha256': hashlib.sha256(b'').hexdigest()},
            'file_sha256': {'fixtures/questions_public_pilot.jsonl':
                           hashlib.sha256(self.questions.read_bytes()).hexdigest()}}))
        self.adapter = self.root / 'adapter.py'
        # Deliberately hostile test double, not a measured candidate.
        self.adapter.write_text('''class TestAdapter:
 def search(self, question, top_k=5):
  return {'hits':[{'document_id':'foreign/project/private','revision':'r1','text':'FORBIDDEN'}]}
def create_adapter(corpus, org, space): return TestAdapter()
''')

    def tearDown(self):
        self.temporary.cleanup()

    def test_leak_aborts_before_second_query_and_does_not_persist_source(self):
        output = self.root / 'results'
        summary = execute('hostile-test-double', self.adapter, self.root,
                          self.questions, output, self.frozen)
        self.assertEqual(summary['status'], 'TENANT_LEAK_ABORT')
        self.assertEqual(summary['questions_executed'], 1)
        trace = (output / 'retrieval.jsonl').read_text()
        self.assertNotIn('FORBIDDEN', trace)
        self.assertIsNone(json.loads(trace)['hits'])

    def test_changed_question_text_cannot_reuse_frozen_ids(self):
        self.questions.write_text(self.questions.read_text().replace('"test"', '"modified"'))
        with self.assertRaisesRegex(ValueError, 'hash changed'):
            execute('test', self.adapter, self.root, self.questions,
                    self.root / 'results', self.frozen)

    def test_adapter_setup_cannot_mutate_public_corpus(self):
        self.adapter.write_text('''from pathlib import Path
def create_adapter(corpus, org, space):
 (Path(corpus)/'unexpected.md').write_text('SDK mutated source')
 return None
''')
        with self.assertRaisesRegex(ValueError, 'setup modified'):
            execute('mutating-test-double', self.adapter, self.root, self.questions,
                    self.root / 'results', self.frozen)


if __name__ == '__main__':
    unittest.main()
