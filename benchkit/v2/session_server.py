"""Loopback broker for question-bound, read-only V2 answer sessions.

Session authority is loaded only from a trusted coordinator-created config file.
There is intentionally no session-creation HTTP endpoint.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, re, resource, sys, threading, time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from benchkit.v2.answer_tool import BoundAnswerTool
from benchkit.v2.integrity import corpus_digest
from benchkit.v2.harness import source_hashes

REPO_ROOT=Path(__file__).resolve().parents[2]
DIRECT_SOURCE=REPO_ROOT/"implementations/v2/luna-vault-direct"
if str(DIRECT_SOURCE) not in sys.path: sys.path.insert(0,str(DIRECT_SOURCE))

MAX_BODY=128*1024
HANDLE_RE=re.compile(r"[A-Za-z0-9_-]{32,256}")
ID_RE=re.compile(r"[A-Za-z0-9_-]{1,100}")

def utc_now(): return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00","Z")
def load_adapter_module(path):
    path=Path(path).resolve(strict=True)
    spec=importlib.util.spec_from_file_location("v2_session_candidate_adapter",path)
    if spec is None or spec.loader is None: raise RuntimeError("cannot load candidate adapter")
    module=importlib.util.module_from_spec(spec); sys.modules[spec.name]=module
    if str(path.parent) not in sys.path: sys.path.insert(0,str(path.parent))
    spec.loader.exec_module(module)
    if not callable(getattr(module,"create_adapter",None)): raise ValueError("candidate adapter must export create_adapter")
    return module

class ScopedCandidateFacade:
    """Normalizes all candidates to scoped filesystem list/read + adapter search."""
    def __init__(self, candidate_adapter, corpus, organization_id, knowledge_space_id, question_id):
        from scoped_vault import ScopedMarkdownVault
        self.candidate_adapter=candidate_adapter
        self.vault=ScopedMarkdownVault(corpus,organization_id,knowledge_space_id)
        self.organization_id=organization_id; self.knowledge_space_id=knowledge_space_id; self.question_id=question_id
    def list_markdown(self):
        return self.vault.list_markdown()
    def read_markdown(self, document_id): return self.vault.read_markdown(document_id)
    def search(self, question, top_k=5):
        q={"id":self.question_id,"organization_id":self.organization_id,
           "knowledge_space_id":self.knowledge_space_id,"question":question}
        return self.candidate_adapter.search(q,top_k=top_k)

class SessionContext:
    def __init__(self, config, token, facade, events_path):
        self.handle=config["handle"]
        # The handle is a random per-session bearer secret; its digest is checked
        # against the root-created record before this context is constructed.
        tool_config={"session_handle":self.handle,"question_id":config["question_id"],
          "organization_id":config["organization_id"],"knowledge_space_id":config["knowledge_space_id"],
          "corpus_root":config["corpus_root"],"token_sha256":config["token_sha256"],
          "max_tool_calls":config.get("max_tool_calls",12),"source_sha256":config.get("corpus_sha256")}
        self.tool=BoundAnswerTool(tool_config,token,facade,events_path=events_path)
        self.question_id=config["question_id"]; self.lock=threading.Lock(); self.events_path=Path(events_path)

class SessionBroker:
    def __init__(self, config_path):
        self.config_path=Path(config_path).resolve(strict=True)
        self.config=json.loads(self.config_path.read_text(encoding="utf-8"))
        self.candidate=self.config["candidate"]
        if not ID_RE.fullmatch(self.config.get("run_id","")): raise ValueError("invalid trusted run_id")
        self.corpus=Path(self.config["corpus_root"]).resolve(strict=True)
        self.events_root=Path(self.config["events_root"]).resolve()
        self.sessions_raw=self.config.get("sessions")
        if not isinstance(self.sessions_raw,list) or not (1<=len(self.sessions_raw)<=20): raise ValueError("trusted config must contain 1..20 sessions")
        self.sessions={}; scope_configs={}; handles=set()
        for raw in self.sessions_raw:
            required=("question_id","organization_id","knowledge_space_id","handle","token_sha256")
            if any(not isinstance(raw.get(k),str) or not raw[k] for k in required): raise ValueError("invalid trusted session entry")
            if not ID_RE.fullmatch(raw["question_id"]): raise ValueError("invalid question ID")
            if not ID_RE.fullmatch(raw["organization_id"]) or not ID_RE.fullmatch(raw["knowledge_space_id"]):
                raise ValueError("invalid trusted principal scope")
            if not HANDLE_RE.fullmatch(raw["handle"]): raise ValueError("session handle must contain 32..256 URL-safe characters")
            if raw["handle"] in handles: raise ValueError("duplicate session handle")
            handles.add(raw["handle"])
            actual=hashlib.sha256(raw["handle"].encode()).hexdigest()
            if not __import__("hmac").compare_digest(actual,raw["token_sha256"]): raise PermissionError("session handle digest differs from trusted config")
            scope=(raw["organization_id"],raw["knowledge_space_id"]); scope_configs.setdefault(scope,[]).append(raw)
        expected=self.config.get("corpus_sha256")
        before=corpus_digest(self.corpus)
        if expected and before!=expected: raise RuntimeError("frozen corpus hash differs before adapter setup")
        source_before=source_hashes(self.config["adapter_path"])
        self.module_load_started=time.perf_counter()
        self.module=load_adapter_module(self.config["adapter_path"])
        self.module_load_elapsed_ms=(time.perf_counter()-self.module_load_started)*1000
        self.adapters={}; self.startup=[]
        for scope in scope_configs:
            before_r=resource.getrusage(resource.RUSAGE_SELF); before_child=resource.getrusage(resource.RUSAGE_CHILDREN)
            started=time.perf_counter(); adapter=self.module.create_adapter(self.corpus,*scope)
            elapsed=(time.perf_counter()-started)*1000
            after_r=resource.getrusage(resource.RUSAGE_SELF); after_child=resource.getrusage(resource.RUSAGE_CHILDREN)
            self.adapters[scope]=adapter
            self.startup.append({"organization_id":scope[0],"knowledge_space_id":scope[1],"adapter_setup_ms":elapsed,
              "own_cpu_user_seconds":after_r.ru_utime-before_r.ru_utime,"own_cpu_system_seconds":after_r.ru_stime-before_r.ru_stime,
              "own_peak_rss_kib":after_r.ru_maxrss,"own_block_input_delta":after_r.ru_inblock-before_r.ru_inblock,"own_block_output_delta":after_r.ru_oublock-before_r.ru_oublock,
              "child_cpu_user_seconds":after_child.ru_utime-before_child.ru_utime,"child_cpu_system_seconds":after_child.ru_stime-before_child.ru_stime,
              "child_block_input_delta":after_child.ru_inblock-before_child.ru_inblock,"child_block_output_delta":after_child.ru_oublock-before_child.ru_oublock})
            if corpus_digest(self.corpus)!=before: raise RuntimeError("adapter setup modified frozen corpus")
        after=corpus_digest(self.corpus)
        if after!=before or (expected and after!=expected): raise RuntimeError("frozen corpus changed during adapter setup")
        self.corpus_hash=after
        source_hash_map=source_hashes(self.config["adapter_path"])
        if source_hash_map!=source_before: raise RuntimeError("candidate source changed during adapter setup")
        declared=self.config.get("source_sha256")
        if declared and declared!=source_hash_map: raise RuntimeError("candidate source hash differs from trusted config")
        for raw in self.sessions_raw:
            scope=(raw["organization_id"],raw["knowledge_space_id"])
            facade=ScopedCandidateFacade(self.adapters[scope],self.corpus,*scope,raw["question_id"])
            event_path=self.events_root/self.config["run_id"]/raw["question_id"]
            event_path.mkdir(parents=True,exist_ok=True)
            ctx=SessionContext({**raw,"corpus_root":str(self.corpus),"corpus_sha256":self.corpus_hash},
                               raw["handle"],facade,event_path/"wrapper.jsonl")
            self.sessions[raw["handle"]]=ctx
        self.startup_manifest={"candidate":self.candidate,"run_id":self.config["run_id"],"corpus_sha256":self.corpus_hash,
          "adapter_path":str(Path(self.config["adapter_path"]).resolve()),"source_sha256":source_hash_map,
          "loaded_scopes":[{"organization_id":x[0],"knowledge_space_id":x[1]} for x in self.adapters],
          "scope_setups":self.startup,"module_load_ms":self.module_load_elapsed_ms,"adapter_setup_excluded_from_session_time":True,
          "native_input_tokens":None,"native_output_tokens":None,"native_tool_calls":None}
        self.events_root.mkdir(parents=True,exist_ok=True)
        (self.events_root/self.config["run_id"]/"startup.json").write_text(json.dumps(self.startup_manifest,indent=2)+"\n",encoding="utf-8")
        self.transport_lock=threading.Lock()
    def close(self):
        for adapter in self.adapters.values():
            if hasattr(adapter,"close"):
                try: adapter.close()
                except Exception: pass
    def record_transport(self,ctx,request_bytes,response_body,status_code,elapsed_ms):
        event={"candidate":self.candidate,"run_id":self.config["run_id"],"question_id":ctx.question_id,
          "wrapper_call":ctx.tool.calls,"timestamp_utc":utc_now(),"http_status":status_code,
          "request_bytes":len(request_bytes),"response_bytes":len(response_body),
          "response_sha256":hashlib.sha256(response_body).hexdigest(),"response_capture":"responses/%04d.json"%ctx.tool.calls,
          "request_sha256":hashlib.sha256(request_bytes).hexdigest(),"request_capture":"requests/%04d.json"%ctx.tool.calls,
          "transport_latency_ms":elapsed_ms*1000,"native_tokens":None}
        response_path=ctx.events_path.parent/event["response_capture"]
        response_path.parent.mkdir(parents=True,exist_ok=True); response_path.write_bytes(response_body)
        request_path=ctx.events_path.parent/event["request_capture"]
        request_path.parent.mkdir(parents=True,exist_ok=True); request_path.write_bytes(request_bytes)
        with self.transport_lock:
            with (ctx.events_path.parent/"transport.jsonl").open("a",encoding="utf-8") as stream:
                stream.write(json.dumps(event,ensure_ascii=False)+"\n")

class BrokerHandler(BaseHTTPRequestHandler):
    server_version="V2ReadOnlyBroker/1"
    def log_message(self,format,*args): return
    def do_GET(self):
        if self.path=="/health":
            body=b'{"status":"ready"}'; self.send_response(200); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
        else: self.send_error(404)
    def do_POST(self):
        if self.path!="/tool": self.send_error(404); return
        handle=self.headers.get("X-Bench-Session","")
        ctx=self.server.broker.sessions.get(handle)
        if ctx is None: self.send_error(403,"unknown session capability"); return
        try: length=int(self.headers.get("Content-Length","-1"))
        except ValueError: self.send_error(400,"invalid content length"); return
        if length<0 or length>MAX_BODY: self.send_error(413,"request body too large"); return
        raw=self.rfile.read(length)
        try: request=json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError,json.JSONDecodeError): self.send_error(400,"request must be UTF-8 JSON"); return
        if not isinstance(request,dict): self.send_error(400,"request must be an object"); return
        started=time.perf_counter()
        with ctx.lock:
            # The handle is added only after lookup in the trusted config map;
            # no org/project/path values come from CLI arguments or caller.
            result=ctx.tool.invoke({**request,"session_handle":ctx.handle})
            status=200 if "error" not in result else (403 if "PermissionError" in result["error"] else 400)
            body=json.dumps(result,ensure_ascii=False,separators=(",",":")).encode("utf-8")
            self.server.broker.record_transport(ctx,raw,body,status,time.perf_counter()-started)
        self.send_response(status); self.send_header("Content-Type","application/json; charset=utf-8"); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)

def serve(config_path,host="127.0.0.1",port=0):
    if host!="127.0.0.1": raise ValueError("session broker must bind only to 127.0.0.1")
    broker=SessionBroker(config_path)
    server=ThreadingHTTPServer((host,port),BrokerHandler); server.daemon_threads=True; server.broker=broker
    try:
        print(json.dumps({"event":"ready","host":host,"port":server.server_address[1],**broker.startup_manifest},ensure_ascii=False),flush=True)
        server.serve_forever()
    finally:
        server.server_close(); broker.close()

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--config",type=Path,required=True); parser.add_argument("--host",default="127.0.0.1"); parser.add_argument("--port",type=int,default=0)
    args=parser.parse_args(); serve(args.config,args.host,args.port)
if __name__=="__main__": main()
