import hashlib,tempfile,unittest
from pathlib import Path
from benchkit.v2.native_prompt import build_prompt,write_assignment
class NativeAssignmentIntegration(unittest.TestCase):
    def test_immutable_question_scope_and_client_schema(self):
        q={'id':'q1','question':'What changed?','organization_id':'org-a','knowledge_space_id':'p1'};token='x'*43
        s={'question_id':'q1','organization_id':'org-a','knowledge_space_id':'p1','handle':token,'token_sha256':hashlib.sha256(token.encode()).hexdigest()}
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'prompt.txt';m=write_assignment(p,'Common policy',q,s,8871,'/workspace/memory-benchmark')
            self.assertEqual(m['prompt_sha256'],hashlib.sha256(p.read_bytes()).hexdigest())
            self.assertIn('"question":"query text"',p.read_text());self.assertIn('python3 /workspace/memory-benchmark/benchkit/v2/session_client.py',p.read_text())
            self.assertIn('Question: What changed?',p.read_text())
        for key,value in [('question_id','q2'),('organization_id','org-b'),('knowledge_space_id','p2'),('token_sha256','wrong')]:
            with self.assertRaises(ValueError):build_prompt('Common policy',q,{**s,key:value},8871,'/workspace/memory-benchmark')
if __name__=='__main__':unittest.main()
