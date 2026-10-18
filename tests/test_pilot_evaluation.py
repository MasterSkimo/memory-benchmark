"""A missing answer is not abstention; exact revisions are mandatory."""
import unittest

from benchkit.evaluate_pilot import grade_answer


class EvaluationValidityTests(unittest.TestCase):
    def test_missing_negative_answer_does_not_receive_credit(self):
        gold = {'organization_id': 'a', 'knowledge_space_id': 'p', 'should_abstain': True}
        self.assertFalse(grade_answer(None, gold, {})['grounded_correct'])

    def test_value_match_with_stale_citation_is_not_grounded(self):
        gold = {'organization_id': 'a', 'knowledge_space_id': 'p', 'should_abstain': False,
                'expected_answer': '7 minutes', 'supporting_document_ids': ['a/p/doc']}
        record = {'status': 'ok', 'answer': 'The target is 7 minutes.',
                  'citations': [{'document_id': 'a/p/doc', 'revision': 'old'}]}
        grade = grade_answer(record, gold, {'a/p/doc': {'revision': 'current'}})
        self.assertTrue(grade['value_match'])
        self.assertFalse(grade['grounded_correct'])
        self.assertEqual(grade['revision_errors'], 1)
