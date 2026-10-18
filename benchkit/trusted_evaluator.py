"""Trusted-only deterministic oracle generation and benchmark scoring.

Run this module ONLY in a separate evaluator workspace with saved candidate traces.
The generator is public for auditability. A shared worktree offers NO security
boundary; do not expose generated oracle outputs to model workers.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .cloud_fixtures import RECOVERY,ACTIONS

def expected(question:dict)->dict:
    """Derive canonical answer and sources from a fixed synthetic scenario."""
    qid=question["id"]
    kind=qid.split("-")[1]
    idx=int(qid.rsplit("-",1)[1])
    org=question["organization_id"]
    project=question["knowledge_space_id"]
    doc=lambda n:f"{org}/{project}/note-{n:03d}"
    answer=None
    citations=[]
    if kind=="exact":
        answer=f"{12+(10+idx)*3} minutes"; citations=[doc(10+idx)]
    elif kind=="semantic":
        answer=RECOVERY[idx]; citations=[doc(20+idx)]
    elif kind=="multihop":
        answer=f"{project}-rb-{idx} ; {ACTIONS[idx]}"; citations=[doc(40+idx),doc(50+idx)]
    elif kind=="temporal":
        answer=f"{90+idx*15} jours"; citations=[doc(70+idx)]
    elif kind=="mutation":
        citations=[doc(90)]
    elif kind not in ("negative","isolation"):
        raise ValueError(f"Unexpected category: {kind}")
    return {"id":qid,"category":kind,"expected_answer":answer,"supporting_document_ids":citations,
            "should_abstain":answer is None,"organization_id":org,"knowledge_space_id":project}

def main()->None:
    """Materialize oracle and score candidate answers with exact normalization."""
    parser=argparse.ArgumentParser()
    parser.add_argument("--questions",type=Path,default=Path("fixtures/questions_public_pilot.jsonl"))
    parser.add_argument("--oracle-output",type=Path,required=True)
    parser.add_argument("--traces",type=Path)
    parser.add_argument("--score-output",type=Path)
    args=parser.parse_args()
    questions=[json.loads(line) for line in args.questions.read_text().splitlines() if line]
    gold=[expected(q) for q in questions]
    args.oracle_output.parent.mkdir(parents=True,exist_ok=True)
    args.oracle_output.write_text("".join(json.dumps(x,ensure_ascii=False)+"\n" for x in gold))
    if not args.traces:return
    if not args.score_output:raise ValueError("--score-output is required with --traces")
    records=[json.loads(x) for x in args.traces.read_text().splitlines() if x]
    observed={r["question_id"]:r for r in records}
    hits=0; leaks=0; traceable=0; tokens=[];tools=[]
    for g in gold:
        r=observed.get(g["id"],{})
        answer=r.get("answer")
        correct=(answer is None or str(answer).strip()=="") if g["should_abstain"] else " ".join(str(answer).strip().casefold().split())==" ".join(str(g["expected_answer"]).strip().casefold().split())
        hits+=int(correct)
        docs=[c.get("document_id") for c in r.get("citations",[]) if isinstance(c,dict)]
        traceable+=int(bool(g["supporting_document_ids"]) and set(g["supporting_document_ids"]).issubset(docs))
        leaks+=sum(not (str(d).startswith(g["organization_id"]+"/"+g["knowledge_space_id"]+"/")) for d in docs)
        usage=r.get("usage") or {}
        if usage.get("input_tokens") is not None and usage.get("output_tokens") is not None:
            tokens.append(usage["input_tokens"]+usage["output_tokens"])
        if r.get("tool_calls") is not None:tools.append(r["tool_calls"])
    report={"status":"INCOMPLETE" if len(observed)!=len(gold) else "COMPLETE",
            "questions":len(gold),"observed":len(observed),"exact_accuracy":hits/len(gold),
            "traceable_answer_fraction":traceable/len(gold),"out_of_scope_citations":leaks,
            "raw_token_sum_measured":sum(tokens) if len(tokens)==len(gold) else None,
            "tool_calls_sum_measured":sum(tools) if len(tools)==len(gold) else None,
            "usage_coverage":len(tokens)/len(gold)}
    args.score_output.parent.mkdir(parents=True,exist_ok=True)
    args.score_output.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))
if __name__=="__main__":main()
