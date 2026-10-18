import json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[4]/"benchkit"/"v2"))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from harness import corpus_digest, run_retrieval

class HarnessIntegrationTests(unittest.TestCase):
 def test_neutral_adapter_contract(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp); scope=root/"vault"/"org-z"/"project-q"; scope.mkdir(parents=True)
   (scope/"a.md").write_text("---\ndocument_id: org-z/project-q/a\norganization_id: org-z\nknowledge_space_id: project-q\nrevision: r1\n---\nA test fact.\n")
   qfile=root/"q.jsonl"; qfile.write_text(json.dumps({"id":"q1","organization_id":"org-z","knowledge_space_id":"project-q","question":"test fact"})+"\n")
   out=run_retrieval("luna-vault-direct",Path(__file__).resolve().parents[1]/"scoped_vault.py",root/"vault",qfile,root/"out")
   self.assertEqual(out["questions_total"],1)
   self.assertEqual(out["successes"],1)
   lines=(root/"out"/"retrieval.jsonl").read_text().splitlines()
   self.assertEqual(len(lines),1)
   self.assertEqual(json.loads(lines[0])["status"],"ok")
   expected=__import__("hashlib").sha256(b"org-z/project-q/a.md\0"+(scope/"a.md").read_bytes()+b"\0").hexdigest()
   self.assertEqual(corpus_digest(root/"vault"),expected)

 def test_frozen_manifest_requires_exact_40_question_ids(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp); scope=root/"vault"/"org-z"/"project-q"; scope.mkdir(parents=True)
   (scope/"a.md").write_text("---\ndocument_id: org-z/project-q/a\nrevision: r1\n---\ntext\n")
   records=[{"id":f"q{i}","organization_id":"org-z","knowledge_space_id":"project-q","question":"text"} for i in range(40)]
   qfile=root/"q.jsonl"; qfile.write_text("\n".join(json.dumps(q) for q in records)+"\n")
   manifest={"questions_sha256":__import__("hashlib").sha256(qfile.read_bytes()).hexdigest(),
             "corpus_sha256":corpus_digest(root/"vault"),"question_ids":[q["id"] for q in records]}
   mfile=root/"manifest.json"; mfile.write_text(json.dumps(manifest))
   result=run_retrieval("luna-vault-direct",Path(__file__).resolve().parents[1]/"scoped_vault.py",root/"vault",qfile,root/"out",mfile)
   self.assertEqual(result["questions_total"],40)
