"""Integration checks for the post-submission grader's key failure cases."""
import tempfile, unittest
from pathlib import Path
from benchkit.v2.evaluate import score_answer, score_retrieval

class GradingIntegration(unittest.TestCase):
    def test_correct_value_requires_current_observed_citation_and_abstention_is_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); scope=root/'org-a/project-01'; scope.mkdir(parents=True)
            doc='org-a/project-01/decision'
            (scope/'decision.md').write_text(f'---\ndocument_id: {doc}\norganization_id: org-a\nknowledge_space_id: project-01\nrevision: r2\n---\nKeep 63 days.')
            g={'id':'q','category':'revision','organization_id':'org-a','knowledge_space_id':'project-01','abstain':False,'required_sources':[{'document_id':doc,'revision':'r2'}],'answer_patterns':[[r'\b63\b']]}
            answer={'answer':'63 days','abstain':False,'citations':[{'document_id':doc,'revision':'r2'}]}
            self.assertFalse(score_answer(answer,g,root,set())['strict_grounded_correct'])
            self.assertTrue(score_answer(answer,g,root,{(doc,'r2')})['strict_grounded_correct'])
            answer['citations'][0]['revision']='r1'
            self.assertFalse(score_answer(answer,g,root,{(doc,'r1')})['strict_grounded_correct'])
            negative={**g,'abstain':True,'required_sources':[],'answer_patterns':[]}
            self.assertFalse(score_answer({'answer':'unknown','citations':[]},negative,root,set())['strict_grounded_correct'])
            self.assertTrue(score_answer({'answer':'not established','abstain':True,'citations':[]},negative,root,set())['strict_grounded_correct'])
    def test_multihop_requires_both_sources_and_negative_empty_is_separate(self):
        g=[{'id':'m','category':'multihop','abstain':False,'organization_id':'a','knowledge_space_id':'p','required_sources':[{'document_id':'a/p/a','revision':'r'},{'document_id':'a/p/b','revision':'r'}]}, {'id':'n','category':'negative','abstain':True,'organization_id':'a','knowledge_space_id':'p','required_sources':[]}]
        rows=[{'question_id':'m','status':'ok','hits':[{'document_id':'a/p/a','revision':'r'}]},{'question_id':'n','status':'ok','hits':[]}]
        got=score_retrieval(rows,g)
        self.assertEqual(got['recall_at_5'],.5)
        self.assertEqual(got['all_required_sources_rate'],0)
        self.assertEqual(got['negative_empty_hit_rate'],1)
if __name__=='__main__': unittest.main()
