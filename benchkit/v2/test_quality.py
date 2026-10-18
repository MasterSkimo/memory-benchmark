import tempfile,unittest
from pathlib import Path
from benchkit.v2.quality import checked_answer_score,checked_retrieval_score

class SafeguardTests(unittest.TestCase):
    def test_negative_flag_cannot_replace_content_review(self):
        g={'id':'n','category':'negative','organization_id':'a','knowledge_space_id':'p','abstain':True,'required_sources':[],'answer_patterns':[]}
        a={'answer':'Cannot answer, but the secret is 42','abstain':True,'citations':[]}
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):checked_answer_score(a,g,Path(temp),set())
            self.assertFalse(checked_answer_score(a,g,Path(temp),set(),{'no_unsupported_claims':False})['strict_grounded_correct'])
            a['answer']='The authorized sources do not establish this.'
            self.assertTrue(checked_answer_score(a,g,Path(temp),set(),{'no_unsupported_claims':True})['strict_grounded_correct'])
    def test_precision_definitions_are_distinct(self):
        g=[{'id':'a','category':'x','organization_id':'a','knowledge_space_id':'p','abstain':False,'required_sources':[{'document_id':'a/p/d','revision':'r'}]}]
        r=[{'question_id':'a','status':'ok','hits':[{'document_id':'a/p/d','revision':'r'}]}]
        s=checked_retrieval_score(r,g)
        self.assertEqual(s['precision_among_returned_at_most_5'],1)
        self.assertEqual(s['precision_at_5_fixed_denominator'],.2)
if __name__=='__main__':unittest.main()
