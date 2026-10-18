"""Neutral V2 retrieval runner. It never imports evaluation or gold data."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, resource, sys, time
from pathlib import Path
try:
    from .integrity import corpus_digest
    from .source_validation import verify_source_revision
except ImportError:
    from integrity import corpus_digest
    from source_validation import verify_source_revision


def sha256_file(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def source_hashes(adapter_path):
    root=Path(adapter_path).resolve().parent
    excluded={"__pycache__", ".venv", "v2env", ".state", "runtime-home", ".models", "site-packages", ".cache"}
    return {str(p.relative_to(root)):sha256_file(p) for p in sorted(root.rglob("*.py"))
            if not excluded.intersection(p.relative_to(root).parts)}
def pct(xs,p):
    if not xs:return None
    s=sorted(xs); x=(len(s)-1)*p; lo=int(x); hi=min(lo+1,len(s)-1)
    return s[lo]+(s[hi]-s[lo])*(x-lo)
def load_adapter(path):
    spec=importlib.util.spec_from_file_location("v2_candidate_adapter",path)
    mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod
    sys.path.insert(0,str(Path(path).resolve().parent))
    spec.loader.exec_module(mod); return mod

def run_retrieval(candidate, adapter_path, corpus_path, questions_path, output_dir, frozen_manifest_path=None):
    corpus=Path(corpus_path).resolve(); qpath=Path(questions_path).resolve(); apath=Path(adapter_path).resolve(); out=Path(output_dir)
    questions=[json.loads(s) for s in qpath.read_text(encoding="utf-8").splitlines() if s.strip()]
    if len({q.get("id",q.get("question_id")) for q in questions}) != len(questions): raise ValueError("question IDs must be unique")
    qhash=sha256_file(qpath); corpus_hash=corpus_digest(corpus)
    frozen=json.loads(Path(frozen_manifest_path).read_text()) if frozen_manifest_path else None
    if frozen:
        expected_q=frozen.get("questions_sha256") or frozen.get("question_file_sha256")
        expected_c=frozen.get("corpus_sha256") or frozen.get("vault_sha256")
        if expected_q and qhash != expected_q: raise ValueError("question file hash differs from freeze")
        if expected_c and corpus_hash != expected_c: raise ValueError("corpus hash differs from freeze")
        frozen_ids=frozen.get("question_ids")
        actual_ids=[q.get("id",q.get("question_id")) for q in questions]
        if len(questions)!=40 or not isinstance(frozen_ids,list) or actual_ids!=frozen_ids:
            raise ValueError("frozen V2 R set must contain exactly the 40 ordered manifest question IDs")
    implementation_sources=source_hashes(apath)
    if frozen and frozen.get("source_sha256"):
        declared=frozen["source_sha256"]
        expected_sources=declared.get(candidate,declared) if isinstance(declared,dict) else None
        if expected_sources and expected_sources!=implementation_sources:
            raise ValueError("candidate source hashes differ from freeze")
    module=load_adapter(apath); adapters={}; setup=[]; rows=[]; out.mkdir(parents=True,exist_ok=True)
    with (out/"retrieval.jsonl").open("w",encoding="utf-8") as stream:
        for q in questions:
            qid=q.get("id",q.get("question_id")); org=q.get("organization_id"); space=q.get("knowledge_space_id")
            if not org or not space: raise ValueError(f"{qid}: fixed organization_id and knowledge_space_id are required")
            key=(org,space); fresh=key not in adapters
            if fresh:
                setup_before=resource.getrusage(resource.RUSAGE_SELF); setup_child_before=resource.getrusage(resource.RUSAGE_CHILDREN)
                start=time.perf_counter(); adapters[key]=module.create_adapter(corpus,org,space)
                setup_after=resource.getrusage(resource.RUSAGE_SELF); setup_child_after=resource.getrusage(resource.RUSAGE_CHILDREN)
                setup.append({"organization_id":org,"knowledge_space_id":space,"elapsed_ms":(time.perf_counter()-start)*1000,
                              "file_reads":getattr(adapters[key],"ingest_file_reads",None),"bytes_read":getattr(adapters[key],"ingest_bytes_read",None),
                              "backend_calls":getattr(adapters[key],"ingest_backend_calls",None),
                              "own_cpu_user_seconds":setup_after.ru_utime-setup_before.ru_utime,
                              "own_cpu_system_seconds":setup_after.ru_stime-setup_before.ru_stime,
                              "own_peak_rss_kib":setup_after.ru_maxrss,
                              "own_block_input_delta":setup_after.ru_inblock-setup_before.ru_inblock,
                              "own_block_output_delta":setup_after.ru_oublock-setup_before.ru_oublock,
                              "child_cpu_user_seconds":setup_child_after.ru_utime-setup_child_before.ru_utime,
                              "child_cpu_system_seconds":setup_child_after.ru_stime-setup_child_before.ru_stime,
                              "child_block_input_delta":setup_child_after.ru_inblock-setup_child_before.ru_inblock,
                              "child_block_output_delta":setup_child_after.ru_oublock-setup_child_before.ru_oublock,
                              "candidate_ingestion_metrics":{name:getattr(adapters[key],name,None) for name in
                                ("ingest_embedding_calls","ingest_embedding_tokens","ingest_elapsed_ms","ingest_seconds","episodes_ingested")}})
                if corpus_digest(corpus)!=corpus_hash: raise ValueError("adapter setup modified corpus")
            adapter=adapters[key]; started=time.perf_counter(); before=resource.getrusage(resource.RUSAGE_SELF); child_before=resource.getrusage(resource.RUSAGE_CHILDREN)
            row={"candidate":candidate,"question_id":qid,"lane":"retrieval","organization_id":org,"knowledge_space_id":space,
                 "top_k":5,"status":"error","input_tokens":None,"output_tokens":None,"native_tool_calls":None,
                 "physical_cache_state":"UNCONTROLLED","source_sha256_before":corpus_digest(corpus)}
            if row["source_sha256_before"]!=corpus_hash: raise ValueError("source changed before query")
            search_started=time.perf_counter()
            try:
                result=adapter.search(q,top_k=5); hits=result["hits"]
                row["backend_search_latency_ms"]=(time.perf_counter()-search_started)*1000
                if len(hits)>5: raise ValueError("adapter exceeded top_k 5")
                prefix=f"{org}/{space}/"
                for hit in hits:
                    if not isinstance(hit.get("document_id"),str) or not hit["document_id"].startswith(prefix): raise PermissionError("TENANT_LEAK: out-of-scope document returned")
                    if not hit.get("revision") or not isinstance(hit.get("text"),str): raise ValueError("hit missing revision or text")
                verification_bytes=sum(verify_source_revision(corpus,org,space,h["document_id"],h["revision"]) for h in hits)
                candidate_metrics={name:result.get(name) for name in
                  ("embedding_calls","embedding_tokens","embedding_vectors","rerank_calls","llm_calls","graph_facts","elapsed_seconds","encoder_input_tokens")
                  if name in result}
                row.update({"status":"ok","hits":hits,"backend_calls":result.get("backend_calls"),"file_reads":result.get("file_reads"),
                            "bytes_read":result.get("bytes_read"),"embedding_calls":result.get("embedding_calls"),
                            "candidate_retrieval_metrics":candidate_metrics,
                            "local_encoder_input_tokens":result.get("encoder_input_tokens",result.get("embedding_tokens")),
                            "wrapper_tool_calls":result.get("tool_calls",getattr(adapter,"tool_calls",None)),
                            "provenance_validation_reads":len(hits),"provenance_validation_bytes":verification_bytes})
            except Exception as e:
                row.setdefault("backend_search_latency_ms",(time.perf_counter()-search_started)*1000)
                row.update({"status":"tenant_leak" if isinstance(e,PermissionError) else "error","error":f"{type(e).__name__}: {e}","hits":None})
            row["source_sha256_after"]=corpus_digest(corpus)
            if row["source_sha256_after"]!=corpus_hash:
                row.update({"status":"integrity_failure","error":"source hash changed during query","hits":None})
            after=resource.getrusage(resource.RUSAGE_SELF); child_after=resource.getrusage(resource.RUSAGE_CHILDREN); row.update({"latency_ms":(time.perf_counter()-started)*1000,
                "end_to_end_guarded_latency_ms":(time.perf_counter()-started)*1000,
                "latency_definition":"end-to-end; includes source guard hashes, adapter search, exact revision validation, and result mapping",
                "cpu_user_seconds":after.ru_utime-before.ru_utime,"cpu_system_seconds":after.ru_stime-before.ru_stime,
                "process_peak_rss_kib":after.ru_maxrss,"own_block_input_delta":after.ru_inblock-before.ru_inblock,
                "own_block_output_delta":after.ru_oublock-before.ru_oublock,
                "child_cpu_user_seconds":child_after.ru_utime-child_before.ru_utime,
                "child_cpu_system_seconds":child_after.ru_stime-child_before.ru_stime,
                "child_block_input_delta":child_after.ru_inblock-child_before.ru_inblock,
                "child_block_output_delta":child_after.ru_oublock-child_before.ru_oublock,
                "cache_condition":"first_scope_query" if fresh else "reused_scope_adapter"})
            rows.append(row); stream.write(json.dumps(row,ensure_ascii=False)+"\n"); stream.flush()
            if row["status"] in ("tenant_leak","integrity_failure"): break
    for a in adapters.values():
        if hasattr(a,"close"): a.close()
    if corpus_digest(corpus)!=corpus_hash: raise ValueError("frozen corpus changed during run")
    good=[r["latency_ms"] for r in rows if r["status"]=="ok"]
    final_sources=source_hashes(apath)
    if final_sources!=implementation_sources: raise ValueError("candidate source changed during retrieval run")
    backend_latencies=[r["backend_search_latency_ms"] for r in rows if r["status"]=="ok"]
    latency_note=("adapter.search timing includes child MCP server startup and query-local indexing" if "basic" in candidate.lower() else "adapter.search call timing")
    summary={"candidate":candidate,"status":"TENANT_LEAK_ABORT" if any(r["status"]=="tenant_leak" for r in rows) else ("SOURCE_INTEGRITY_ABORT" if any(r["status"]=="integrity_failure" for r in rows) else ("RETRIEVAL_TESTED" if len(good)==len(questions) else "INCOMPLETE")),
      "questions_total":len(questions),"questions_executed":len(rows),"successes":len(good),
      "latency_ms":{"p50":pct(good,.5),"p95":pct(good,.95),"definition":"guard-inclusive end-to-end"},
      "backend_search_latency_ms":{"p50":pct(backend_latencies,.5),"p95":pct(backend_latencies,.95),"definition":latency_note+"; excludes outer corpus guards and revision validation"},
      "setups":setup,"setup_excluded_from_query_latency":True,"questions_sha256":qhash,"corpus_sha256":corpus_hash,
      "adapter_sha256":sha256_file(apath),"source_sha256":implementation_sources,
      "native_token_coverage":0,"native_token_counter_source":"NOT_AVAILABLE","scoring":"NOT_RUN; separate evaluator required"}
    (out/"retrieval-summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8"); return summary

def main():
    p=argparse.ArgumentParser(); p.add_argument("--candidate",required=True); p.add_argument("--adapter",type=Path,required=True); p.add_argument("--corpus",type=Path,required=True); p.add_argument("--questions",type=Path,required=True); p.add_argument("--out",type=Path,required=True); p.add_argument("--frozen-manifest",type=Path)
    a=p.parse_args(); print(json.dumps(run_retrieval(a.candidate,a.adapter,a.corpus,a.questions,a.out,a.frozen_manifest),indent=2))
if __name__=="__main__":main()
