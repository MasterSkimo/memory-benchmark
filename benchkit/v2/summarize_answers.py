"""Evaluate submitted native answers against independently exported gold."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from .evaluate import load_jsonl, parse_answer, fraction
from .quality import checked_answer_score
from .harness import pct


def citations_in(value):
    found=set()
    if isinstance(value,dict):
        if isinstance(value.get('document_id'),str) and isinstance(value.get('revision'),str):
            found.add((value['document_id'],value['revision']))
        for child in value.values(): found |= citations_in(child)
    elif isinstance(value,list):
        for child in value: found |= citations_in(child)
    return found


def summarize(candidate, gold_path, run_id='v2-pilot-20261018'):
    root=Path('results/v2')/candidate; frozen=json.loads(Path('results/v2/frozen-evaluation.json').read_text())
    gold={g['id']:g for g in load_jsonl(gold_path)}; rows=[]
    review_path=Path('results/v2/negative-claim-review.json')
    claim_reviews=json.loads(review_path.read_text())['reviews'] if review_path.exists() else {}
    audit=json.loads(Path('results/v2/harness/prompt-audit.json').read_text())
    eligible=audit['sessions'][candidate]
    common_ids=set(audit['common_unassisted_question_ids'])
    for qid in frozen['answer_question_ids']:
        rawpath=root/'answers/raw'/f'{qid}.txt'; session=root/'answer-events'/run_id/qid
        wrapper=load_jsonl(session/'wrapper.jsonl') if (session/'wrapper.jsonl').exists() else []
        transport=load_jsonl(session/'transport.jsonl') if (session/'transport.jsonl').exists() else []
        observed=set(); verified_responses=0
        for event in transport:
            p=session/event['response_capture']; raw=p.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=event['response_sha256']: raise ValueError('response bytes differ from recorded SHA')
            observed |= citations_in(json.loads(raw).get('result')); verified_responses+=1
        score=None; error=None
        if rawpath.exists() and eligible.get(qid,{}).get('eligible_for_quality_score',False):
            try:
                answer=parse_answer(rawpath.read_text());
                if answer.get('question_id')!=qid: raise ValueError('wrong question ID')
                score=checked_answer_score(answer,gold[qid],Path('fixtures/v2/vault'),observed,claim_reviews.get(candidate,{}).get(qid))
            except Exception as exc:
                error=f'{type(exc).__name__}: {exc}'
                score={'question_id':qid,'category':gold[qid]['category'],'abstain_expected':bool(gold[qid]['abstain']),
                       'abstain_observed':False,'component_correct':False,'citation_complete':False,
                       'strict_grounded_correct':False,'obsolete_citations':0,'grading_error':error}
        elif rawpath.exists(): error='NOT_SCORED: '+','.join(eligible[qid]['issues'])
        else: error='No submitted answer; see interrupted-session evidence when present'
        rows.append({'candidate':candidate,'question_id':qid,'status':'submitted' if rawpath.exists() else 'interrupted',
                     'score':score,'error':error,'prompt_audit':eligible.get(qid,{'eligible_for_quality_score':False,'issues':['no_submitted_final']}),'wrapper_calls':len(wrapper),
                     'wrapper_operations':{op:sum(e.get('operation')==op for e in wrapper) for op in ('list','read','search')},
                     'wrapper_errors':sum(e['status']!='ok' for e in wrapper),'transport_response_bytes':sum(e['response_bytes'] for e in transport),
                     'transport_request_bytes':sum(e['request_bytes'] for e in transport),'verified_response_captures':verified_responses,
                     'wrapper_operation_latency_ms':sum(e.get('operation_latency_ms',0) for e in wrapper),
                     'wrapper_total_latency_ms':sum(e['wrapper_latency_ms'] for e in wrapper),
                     'observed_citations':[{'document_id':d,'revision':r} for d,r in sorted(observed)],
                     'native_input_tokens':None,'native_cached_tokens':None,'native_output_tokens':None,'native_reasoning_tokens':None,'native_tool_calls':None})
    complete=[r for r in rows if r['score'] is not None]; positives=[r for r in complete if not r['score']['abstain_expected']]; negatives=[r for r in complete if r['score']['abstain_expected']]
    paired=[r for r in complete if r['question_id'] in common_ids]
    summary={'candidate':candidate,'planned_sessions':20,'submitted_answers':sum(r['status']=='submitted' for r in rows),'scorable_answers':len(complete),'interrupted_sessions':sum(r['status']=='interrupted' for r in rows),
             'strict_grounded_correct':sum(r['score']['strict_grounded_correct'] for r in complete),
             'strict_grounded_rate_completed':fraction([r['score']['strict_grounded_correct'] for r in complete]),
             'strict_grounded_rate_planned_20':None,
             'full_set_quality_status':'INCOMPLETE: uncaptured or mismatched actual prompts are not scored',
             'component_correct_rate':fraction([r['score']['component_correct'] for r in positives]),
             'citation_complete_rate':fraction([r['score']['citation_complete'] for r in positives]),
             'negative_abstention_rate':fraction([r['score']['strict_grounded_correct'] for r in negatives]),
             'obsolete_citations':sum(r['score']['obsolete_citations'] for r in complete),
             'paired_question_count':len(paired),'paired_question_ids':sorted(common_ids),
             'paired_definition':'Intersection of verified actual prompts for all engines, excluding documented same-session advice and launcher cohort; post-dispatch audit subset',
             'paired_strict_grounded_rate':fraction([r['score']['strict_grounded_correct'] for r in paired]),
             'paired_wrapper_calls_mean':fraction([r['wrapper_calls'] for r in paired]),
             'paired_response_bytes_mean':fraction([r['transport_response_bytes'] for r in paired]),
             'wrapper_calls_total':sum(r['wrapper_calls'] for r in rows),'wrapper_errors':sum(r['wrapper_errors'] for r in rows),
             'transport_response_bytes_total':sum(r['transport_response_bytes'] for r in rows),
             'wrapper_operations':{op:sum(r['wrapper_operations'][op] for r in rows) for op in ('list','read','search')},
             'native_token_coverage':0,'native_tool_export_coverage':0,'native_tokens':None,'native_tool_calls':None,
             'causal_status':'EXPLORATORY: shared filesystem and unrestricted native tools; equivalent policy/API but no enforced native capability parity',
             'scores':rows}
    summary['wrapper_operations']['other_or_missing']=summary['wrapper_calls_total']-sum(summary['wrapper_operations'].values())
    (root/'answers/evaluation.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    return summary


def main():
    p=argparse.ArgumentParser();p.add_argument('--candidate',required=True);p.add_argument('--gold',type=Path,required=True);a=p.parse_args()
    s=summarize(a.candidate,a.gold);print(json.dumps({k:v for k,v in s.items() if k!='scores'},indent=2))
if __name__=='__main__':main()
