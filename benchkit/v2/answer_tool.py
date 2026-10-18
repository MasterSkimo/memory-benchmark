"""Shared question-bound read-only tool interface for native Luna answer runs."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib, hmac, json, re, time
from pathlib import Path
try:
    from .source_validation import verify_source_revision
except ImportError:
    from source_validation import verify_source_revision

SCOPE_FIELDS={"organization_id","knowledge_space_id","org","project","tenant","corpus_root","path","tenant_filter"}

def utc_now(): return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00","Z")
def digest_tree(root):
    h=hashlib.sha256(); root=Path(root); count=0; total=0
    for p in sorted(root.rglob("*.md")):
        if p.is_symlink(): raise PermissionError("symlinked source rejected")
        data=p.read_bytes(); count+=1; total+=len(data)
        h.update(p.relative_to(root).as_posix().encode("utf-8")); h.update(b"\0"); h.update(data); h.update(b"\0")
    return h.hexdigest(),count,total

def validate_result(result, operation, prefix, corpus, organization_id, knowledge_space_id):
    """Fail closed if a backend maps foreign or unprovenanced data into output."""
    if operation=="list":
        values=result if isinstance(result,list) else result.get("documents",result.get("items")) if isinstance(result,dict) else None
        if not isinstance(values,list): raise ValueError("list result must be a document list")
        for item in values:
            docid=item if isinstance(item,str) else item.get("document_id") if isinstance(item,dict) else None
            if not isinstance(docid,str) or not docid.startswith(prefix): raise PermissionError("out-of-scope list item rejected")
    elif operation=="read":
        value=result
        if isinstance(value,dict) and "document" in value: value=value["document"]
        docid=value.get("document_id") if isinstance(value,dict) else None
        if not isinstance(docid,str) or not docid.startswith(prefix): raise PermissionError("out-of-scope read result rejected")
        if not value.get("revision"): raise ValueError("read result is missing exact revision")
        verify_source_revision(corpus,organization_id,knowledge_space_id,docid,value["revision"])
    else:
        hits=result.get("hits") if isinstance(result,dict) else result
        if not isinstance(hits,list): raise ValueError("search result must contain a hits list")
        for hit in hits:
            if not isinstance(hit,dict) or not isinstance(hit.get("document_id"),str) or not hit["document_id"].startswith(prefix):
                raise PermissionError("out-of-scope search hit rejected")
            if not hit.get("revision"): raise ValueError("search hit is missing exact revision")
            verify_source_revision(corpus,organization_id,knowledge_space_id,hit["document_id"],hit["revision"])
    return result

class BoundAnswerTool:
    """Read-only per-question policy API with authority fixed outside model input.

    config is coordinator-created and carries the trusted principal, corpus,
    opaque session handle, and token digest. Calls from the model cannot select
    or override any of those fields.
    """
    def __init__(self, config, token, adapter, events_path=None):
        self.config=config; self.adapter=adapter; self.events_path=Path(events_path) if events_path else None
        if not isinstance(config,dict): raise ValueError("session config must be an object")
        for key in ("session_handle","question_id","organization_id","knowledge_space_id","corpus_root","token_sha256"):
            if not isinstance(config.get(key),str) or not config[key]: raise ValueError("invalid session config")
        if not hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(),config["token_sha256"]): raise PermissionError("session token rejected")
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,128}",config["session_handle"]): raise ValueError("invalid session handle")
        self.token=token; self.max_calls=int(config.get("max_tool_calls",12)); self.calls=0
        if self.events_path and self.events_path.exists():
            for line in self.events_path.read_text(encoding="utf-8").splitlines():
                try:
                    if json.loads(line).get("question_id")==config["question_id"]: self.calls+=1
                except json.JSONDecodeError: raise ValueError("malformed existing wrapper audit log")
        self.expected_source_sha256=config.get("source_sha256")

    def invoke(self, request):
        started=time.perf_counter(); wall_start=utc_now(); error=None; result=None; operation=request.get("op") if isinstance(request,dict) else None
        self.calls+=1
        try:
            if self.calls>self.max_calls: raise RuntimeError("question tool-call budget exhausted")
            if not isinstance(request,dict) or request.get("session_handle")!=self.config["session_handle"]: raise PermissionError("session handle mismatch")
            if not hmac.compare_digest(hashlib.sha256(self.token.encode()).hexdigest(),self.config["token_sha256"]): raise PermissionError("session token rejected")
            if SCOPE_FIELDS.intersection(request): raise PermissionError("scope and path overrides are forbidden")
            if operation not in ("list","read","search"): raise ValueError("operation must be list, read, or search")
            allowed={"list":{"op","session_handle"},"read":{"op","session_handle","document_id"},
                     "search":{"op","session_handle","question","top_k"}}[operation]
            extra=set(request)-allowed
            if extra: raise PermissionError("unsupported tool request fields: "+", ".join(sorted(extra)))
            before,before_count,before_bytes=digest_tree(self.config["corpus_root"])
            if self.expected_source_sha256 and before!=self.expected_source_sha256: raise RuntimeError("frozen source hash mismatch before call")
            call=time.perf_counter()
            if operation=="list":
                if hasattr(self.adapter,"list_markdown"):
                    prefix=f"{self.config['organization_id']}/{self.config['knowledge_space_id']}/"
                    result=[(str(item) if str(item).startswith(prefix) else prefix+str(item).removesuffix(".md"))
                            for item in self.adapter.list_markdown()]
                elif hasattr(self.adapter,"list_documents"): result=self.adapter.list_documents()
                else: raise NotImplementedError("candidate does not expose read-only list")
            elif operation=="read":
                docid=request.get("document_id")
                if not isinstance(docid,str) or not docid.startswith(f"{self.config['organization_id']}/{self.config['knowledge_space_id']}/"):
                    raise PermissionError("document is outside bound scope")
                if hasattr(self.adapter,"read_markdown"): result=self.adapter.read_markdown(docid)
                elif hasattr(self.adapter,"read"): result=self.adapter.read(docid)
                else: raise NotImplementedError("candidate does not expose read-only read")
            else:
                question=request.get("question")
                if not isinstance(question,str) or not question.strip(): raise ValueError("question must be non-empty text")
                top_k=request.get("top_k",5)
                if type(top_k) is not int or not 1<=top_k<=5: raise ValueError("top_k must be 1..5")
                q={"id":self.config["question_id"],"organization_id":self.config["organization_id"],"knowledge_space_id":self.config["knowledge_space_id"],"question":question}
                if hasattr(self.adapter,"list_markdown"):
                    result=self.adapter.search(question,top_k=top_k)
                else:
                    result=self.adapter.search(q,top_k=top_k)
            op_ms=(time.perf_counter()-call)*1000
            after,after_count,after_bytes=digest_tree(self.config["corpus_root"])
            if after!=before or (self.expected_source_sha256 and after!=self.expected_source_sha256):
                raise RuntimeError("source changed during tool call")
            result=validate_result(result,operation,f"{self.config['organization_id']}/{self.config['knowledge_space_id']}/",
                                   self.config["corpus_root"],self.config["organization_id"],self.config["knowledge_space_id"])
            backend_calls=result.get("backend_calls") if isinstance(result,dict) else None
            reads=result.get("file_reads") if isinstance(result,dict) else None
            bytes_read=result.get("bytes_read") if isinstance(result,dict) else None
            event={"question_id":self.config["question_id"],"wrapper_call":self.calls,"operation":operation,"status":"ok","timestamp_utc":wall_start,
                   "wrapper_latency_ms":(time.perf_counter()-started)*1000,"operation_latency_ms":op_ms,"backend_calls":backend_calls,
                   "file_reads":reads,"bytes_read":bytes_read,"source_sha256_before":before,"source_sha256_after":after,
                   "integrity_guard_file_reads":before_count+after_count,"integrity_guard_bytes_scanned":before_bytes+after_bytes}
            self._log(event); return {"result":result,"audit":event}
        except Exception as exc:
            error=f"{type(exc).__name__}: {exc}"
            event={"question_id":self.config["question_id"],"wrapper_call":self.calls,"operation":operation,"status":"error","timestamp_utc":wall_start,
                   "wrapper_latency_ms":(time.perf_counter()-started)*1000,"error":error}
            self._log(event); return {"error":error,"audit":event}
    def _log(self,event):
        if self.events_path:
            self.events_path.parent.mkdir(parents=True,exist_ok=True)
            with self.events_path.open("a",encoding="utf-8") as f:f.write(json.dumps(event,ensure_ascii=False)+"\n")
