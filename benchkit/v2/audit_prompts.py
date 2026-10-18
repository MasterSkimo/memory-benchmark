"""Validate captured native assignments against frozen questions and capabilities."""
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path

def main():
    root=Path('results/v2');questions={q['id']:q for q in map(json.loads,Path('fixtures/v2/questions.jsonl').read_text().splitlines())}
    rows=[json.loads(l) for l in (root/'harness/native-E-prompts.jsonl').read_text().splitlines()]
    latest={(r['candidate'],r['question_id']):r for r in rows}
    dispatch=[json.loads(l) for l in (root/'harness/native-E-dispatch.jsonl').read_text().splitlines()]
    common=' '.join(Path('benchkit/v2/answer-prompt.txt').read_text().split());result={};intervals=[]
    for d in dispatch:
        c,qid=d['candidate'],d['question_id'];p=latest.get((c,qid));issues=[];elapsed=None
        if not p:issues=['prompt_not_captured']
        else:
            q=questions[qid];text=p['redacted_prompt']
            if f"Question ID: {qid}\n" not in text:issues.append('question_id_mismatch')
            if 'Question: '+q['question']+'\n' not in text:issues.append('question_text_mismatch')
            if f"Authorized scope label: {q['organization_id']} / {q['knowledge_space_id']}\n" not in text:issues.append('scope_label_mismatch')
            if ' '.join(text.split('Question ID:',1)[0].split())!=common:issues.append('common_policy_mismatch')
            if p['task_name']!=d['agent_identity'].split('/')[-1]:issues.append('agent_assignment_mismatch')
            config=json.loads(Path('/tmp',f'bench-v2-{c}-sessions.json').read_text());handle=next(s['handle'] for s in config['sessions'] if s['question_id']==qid)
            if hashlib.sha256(text.replace('[REDACTED_CAPABILITY]',handle).encode()).hexdigest()!=p['full_prompt_sha256']:issues.append('capability_or_prompt_hash_mismatch')
            if p.get('dispatch_time_utc') and d.get('final_received_time_utc'):
                elapsed=(datetime.fromisoformat(d['final_received_time_utc'])-datetime.fromisoformat(p['dispatch_time_utc'])).total_seconds()
                if elapsed<0:issues.append('negative_clock_interval');elapsed=None
                else:intervals.append({'candidate':c,'question_id':qid,'elapsed_seconds':elapsed})
        result.setdefault(c,{})[qid]={'eligible_for_quality_score':not issues,'issues':issues,'prompt_captured':p is not None,'dispatcher_elapsed_seconds':elapsed}
    valid={c:{qid for qid,v in scores.items() if v['eligible_for_quality_score']} for c,scores in result.items()}
    matched=sorted(set.intersection(*valid.values()))
    audit={'audited_at_utc':datetime.now(timezone.utc).isoformat(),'source':'Exact saved prompts, frozen question text/principal, native task identity, private config capabilities and recorded full-prompt SHA256. Only capability digests are exported.','captured_unique_prompts':len(latest),'prepared_prompt_records':len(rows),'prompt_quality_eligible_count':sum(len(v) for v in valid.values()),'common_verified_question_ids':matched,'common_unassisted_question_ids':[qid for qid in matched if qid not in {'v2-sem-01','v2-mh-05','v2-mh-06'}],'sessions':result}
    (root/'harness/prompt-audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    (root/'telemetry-coverage.json').write_text(json.dumps({'native_tokens':None,'native_tool_calls':None,'native_token_coverage':0,'submitted_native_finals':len(dispatch),'prompt_captures':len(latest),'verified_prompt_quality_coverage_count':sum(len(v) for v in valid.values()),'dispatcher_elapsed_coverage_count':len(intervals),'dispatcher_elapsed_intervals':intervals,'native_serving_latency':None,'native_snapshot':None},indent=2)+'\n')
    print(json.dumps({'eligible':{c:len(v) for c,v in valid.items()},'common_verified_ids':matched,'common_unassisted_ids':audit['common_unassisted_question_ids']},indent=2))
if __name__=='__main__':main()
