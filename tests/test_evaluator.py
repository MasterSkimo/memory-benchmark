"""Pure offline checks for trusted answer scoring."""
import unittest
from benchkit.trusted_evaluator import expected
class TrustedEvaluatorTest(unittest.TestCase):
    def test_exact_and_temporal(self):
        """Expected values must follow the public fixture's deterministic cases."""
        q={"organization_id":"org-alpha","knowledge_space_id":"project-01","id":"q00-exact-0"}
        self.assertEqual(expected(q)["expected_answer"],"42 minutes")
        q["id"]="q00-temporal-2"
        self.assertEqual(expected(q)["expected_answer"],"120 jours")
    def test_isolation_has_no_answer(self):
        """Foreign-scope requests must abstain."""
        q={"organization_id":"org-alpha","knowledge_space_id":"project-01","id":"q00-isolation-0"}
        self.assertTrue(expected(q)["should_abstain"])
if __name__=="__main__":unittest.main()
