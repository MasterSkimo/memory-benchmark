"""Live loopback broker integration and authority-bound citation tests."""
import hashlib, http.client, json, secrets, sys, tempfile, threading, unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from benchkit.v2.integrity import corpus_digest
from benchkit.v2.session_server import BrokerHandler, SessionBroker

REPO=Path(__file__).resolve().parents[2]
DIRECT=REPO/"implementations/v2/luna-vault-direct"

class SessionBrokerIntegrationTests(unittest.TestCase):
 def test_bound_list_read_search_and_forgery_rejection(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp); corpus=root/"vault"; scope=corpus/"org-demo"/"project-01"; scope.mkdir(parents=True)
   (scope/"note.md").write_text("---\ndocument_id: org-demo/project-01/note\norganization_id: org-demo\nknowledge_space_id: project-01\nrevision: r1\n---\nA current decision for testing the broker.\n")
   handle=secrets.token_urlsafe(32)
   config={"candidate":"luna-vault-direct","run_id":"test-run","adapter_path":str(DIRECT/"scoped_vault.py"),"corpus_root":str(corpus),"corpus_sha256":corpus_digest(corpus),"events_root":str(root/"events"),
      "sessions":[{"question_id":"q-test","organization_id":"org-demo","knowledge_space_id":"project-01","handle":handle,"token_sha256":hashlib.sha256(handle.encode()).hexdigest(),"max_tool_calls":12}]}
   path=root/"sessions.json"; path.write_text(json.dumps(config))
   broker=SessionBroker(path); server=ThreadingHTTPServer(("127.0.0.1",0),BrokerHandler); server.broker=broker; server.daemon_threads=True
   thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
   def post(body,capability=handle):
    conn=http.client.HTTPConnection("127.0.0.1",server.server_address[1],timeout=5)
    conn.request("POST","/tool",body=json.dumps(body).encode(),headers={"Content-Type":"application/json","X-Bench-Session":capability})
    response=conn.getresponse(); data=response.read(); status=response.status; conn.close()
    try: parsed=json.loads(data)
    except json.JSONDecodeError: parsed={"error":data.decode("utf-8",errors="replace")}
    return status,data,parsed
   try:
    status,_,listed=post({"op":"list"})
    self.assertEqual(status,200); self.assertEqual(listed["result"],["org-demo/project-01/note"])
    status,raw,search=post({"op":"search","question":"current decision"})
    self.assertEqual(status,200); self.assertTrue(search["result"]["hits"])
    citation=search["result"]["hits"][0]
    self.assertEqual(citation["document_id"],"org-demo/project-01/note")
    status,_,read=post({"op":"read","document_id":citation["document_id"]})
    self.assertEqual(status,200); self.assertEqual(read["result"]["revision"],citation["revision"])
    self.assertEqual(read["result"]["revision"],"r1")
    response_file=root/"events"/"test-run"/"q-test"/"responses"/"0002.json"
    self.assertEqual(response_file.read_bytes(),raw)
    status,_,forged=post({"op":"search","question":"decision","organization_id":"org-demo"})
    self.assertEqual(status,403); self.assertIn("scope",forged["error"].lower())
    status,_,wrong=post({"op":"list"},"Z"*43)
    self.assertEqual(status,403)
    self.assertFalse((root/"events"/"test-run"/"q-test"/"responses"/"0005.json").exists())
   finally:
    server.shutdown(); server.server_close(); broker.close(); thread.join(timeout=2)

if __name__=="__main__": unittest.main()
