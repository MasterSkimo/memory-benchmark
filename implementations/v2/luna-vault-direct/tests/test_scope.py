import hashlib, json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[4]/"benchkit"/"v2"))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scoped_vault import ScopedMarkdownVault, ScopeError
from answer_tool import BoundAnswerTool

class DirectV2SecurityTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)/"vault"; p=self.root/"org-a"/"project-x"; p.mkdir(parents=True)
  (p/"one.md").write_text("---\ndocument_id: org-a/project-x/one\norganization_id: org-a\nknowledge_space_id: project-x\nrevision: r1\n---\nhello evidence\n")
  foreign=self.root/"org-a"/"project-y"; foreign.mkdir(); (foreign/"secret.md").write_text("secret")
  self.token="opaque-random-token-for-test"; self.config={"session_handle":"handle_1234567890123456","question_id":"q1","organization_id":"org-a","knowledge_space_id":"project-x","corpus_root":str(self.root),"token_sha256":hashlib.sha256(self.token.encode()).hexdigest(),"max_tool_calls":5}
 def tearDown(self): self.tmp.cleanup()
 def test_scope_and_source_metadata(self):
  v=ScopedMarkdownVault(self.root,"org-a","project-x")
  self.assertEqual(v.read_markdown("one")["revision"],"r1")
  with self.assertRaises(ScopeError): v.read_markdown("org-a/project-y/secret")
  first=v.search("hello"); second=v.search("hello")
  self.assertEqual(first["file_reads"],second["file_reads"])
  self.assertEqual(first["bytes_read"],second["bytes_read"])
 def test_handle_token_and_scope_forgery_rejected(self):
  with self.assertRaises(PermissionError): BoundAnswerTool(self.config,"wrong",ScopedMarkdownVault(self.root,"org-a","project-x"))
  auth=BoundAnswerTool(self.config,self.token,ScopedMarkdownVault(self.root,"org-a","project-x"))
  self.assertIn("handle mismatch",auth.invoke({"session_handle":"foreign_handle_123456","op":"list"})["error"])
  self.assertIn("forbidden",auth.invoke({"session_handle":self.config["session_handle"],"op":"list","organization_id":"org-a"})["error"])
 def test_answer_interface_scope_and_top_k(self):
  tool=BoundAnswerTool(self.config,self.token,ScopedMarkdownVault(self.root,"org-a","project-x"))
  ok=tool.invoke({"session_handle":self.config["session_handle"],"op":"search","question":"hello","top_k":5})
  self.assertEqual(ok["audit"]["status"],"ok",ok)
  self.assertEqual(ok["result"]["hits"][0]["revision"],"r1")
  listed=tool.invoke({"session_handle":self.config["session_handle"],"op":"list"})
  self.assertEqual(listed["result"],["org-a/project-x/one"])
  bad=tool.invoke({"session_handle":self.config["session_handle"],"op":"search","question":"x","organization_id":"org-a","top_k":1})
  self.assertIn("forbidden",bad["error"])
 def test_result_mapping_rejects_stale_revision(self):
  class StaleAdapter:
   def search(self,question,top_k=5):
    return {"hits":[{"document_id":"org-a/project-x/one","revision":"r0","score":1.0,"text":"stale"}]}
  tool=BoundAnswerTool(self.config,self.token,StaleAdapter())
  result=tool.invoke({"session_handle":self.config["session_handle"],"op":"search","question":"hello"})
  self.assertIn("revision differs",result["error"])
if __name__=="__main__":unittest.main()
