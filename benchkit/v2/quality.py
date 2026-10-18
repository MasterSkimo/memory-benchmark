"""Post-pilot safeguards for the frozen low-level score definitions.

Frozen component matching is preserved. A negative flag alone never establishes
absence of unsupported claims; the final summary requires a separate content
review. No candidate retrieval or answer behavior is changed by this module.
"""
from .evaluate import score_answer, score_retrieval


def checked_answer_score(answer, gold, corpus, observed_sources, claim_review=None):
    result=score_answer(answer,gold,corpus,observed_sources)
    if gold['abstain']:
        if not isinstance(claim_review,dict) or type(claim_review.get('no_unsupported_claims')) is not bool:
            raise ValueError('Negative answer requires explicit coordinator content review')
        result['abstention_flag_score']=result['strict_grounded_correct']
        result['claim_review']=claim_review
        result['strict_grounded_correct']=bool(result['abstention_flag_score'] and claim_review['no_unsupported_claims'])
    return result


def checked_retrieval_score(rows,gold):
    result=score_retrieval(rows,gold)
    result['precision_among_returned_at_most_5']=result.pop('precision_at_5')
    keyed={g['id']:g for g in gold};values=[]
    for row in rows:
        g=keyed[row['question_id']]
        if not g['required_sources']: continue
        wanted={(x['document_id'],x['revision']) for x in g['required_sources']}
        got={(x['document_id'],x['revision']) for x in (row.get('hits') or [])}
        values.append(len(wanted&got)/5)
    result['precision_at_5_fixed_denominator']=sum(values)/len(values) if values else None
    result['precision_definition']='Both metrics reported: correct/returned and correct/5; macro over answerable questions only.'
    for s in result['scores']:
        s['precision_among_returned_at_most_5']=s.pop('precision_at_5')
    return result
