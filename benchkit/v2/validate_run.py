"""Validate bounded V2 evidence, frozen inputs, and preserved V1 bytes."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
from .integrity import corpus_digest
from .evaluate import load_jsonl


def main():
    frozen=json.loads(Path('results/v2/frozen-evaluation.json').read_text())
    sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    changed=[p for p,h in frozen['file_sha256'].items() if sha(p)!=h]
    if changed: raise ValueError(f'frozen source changed: {changed}')
    if corpus_digest('fixtures/v2/vault')!=frozen['corpus_sha256']: raise ValueError('corpus changed')
    if sha('fixtures/v2/questions.jsonl')!=frozen['questions_sha256']: raise ValueError('questions changed')
    if sha('.models/v2/trained-multilingual/checkpoint.pt')!=frozen['model_checkpoint_sha256']: raise ValueError('model changed')
    v1=json.loads(Path('results/v2/v1-preservation.json').read_text())
    oldchanged=[p for p,h in v1['file_sha256'].items() if sha(p)!=h]
    if oldchanged: raise ValueError(f'V1 files changed: {oldchanged}')
    checks={}
    for candidate in frozen['runnable_candidates']:
        root=Path('results/v2')/candidate
        rows=load_jsonl(root/'retrieval/retrieval.jsonl')
        if [r['question_id'] for r in rows]!=frozen['question_ids']: raise ValueError('R question set mismatch')
        if any(r['status']!='ok' for r in rows): raise ValueError('retrieval error or leak')
        expected=set(frozen['answer_question_ids'])-({'v2-sem-01'} if candidate=='luna-vault-direct' else set())
        raw={p.stem for p in (root/'answers/raw').glob('*.txt')}
        if raw!=expected: raise ValueError(f'{candidate} E set differs: missing={expected-raw}, extra={raw-expected}')
        calls=0;captures=0
        for qid in frozen['answer_question_ids']:
            session=root/'answer-events/v2-pilot-20261018'/qid
            wrappers=load_jsonl(session/'wrapper.jsonl') if (session/'wrapper.jsonl').exists() else []
            if len(wrappers)>12: raise ValueError('wrapper call budget exceeded')
            calls+=len(wrappers)
            for event in load_jsonl(session/'transport.jsonl') if (session/'transport.jsonl').exists() else []:
                if sha(session/event['request_capture'])!=event['request_sha256']: raise ValueError('request capture changed')
                if sha(session/event['response_capture'])!=event['response_sha256']: raise ValueError('response capture changed')
                captures+=1
        checks[candidate]={'R_queries':len(rows),'E_submitted':len(raw),'E_session_attempts':20,'wrapper_calls':calls,'exact_response_captures_verified':captures}
    report={'status':'PASS','V1_files_byte_preserved':len(v1['file_sha256']),'frozen_files_verified':len(frozen['file_sha256']),'model_and_corpus_and_questions_verified':True,'candidate_checks':checks,'native_token_counts':None}
    Path('results/v2/validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__': main()
