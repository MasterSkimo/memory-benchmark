"""Post-submission evaluation; never imported by candidate adapters or tools."""
from __future__ import annotations
import argparse, json, re, statistics, unicodedata
from pathlib import Path
from .source_validation import verify_source_revision


def load_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def normal(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(text).casefold()) if not unicodedata.combining(c))


def fraction(values):
    return statistics.mean(values) if values else None


def score_retrieval(rows, gold):
    keyed = {g['id']: g for g in gold}
    scores = []
    for row in rows:
        g = keyed[row['question_id']]
        hits = row.get('hits') or []
        required = {(s['document_id'], s['revision']) for s in g['required_sources']}
        got = [(s['document_id'], s['revision']) for s in hits]
        correct = set(got) & required
        negative = bool(g['abstain'])
        reciprocal = next((1 / rank for rank, s in enumerate(got, 1) if s in required), 0) if required else None
        scores.append({'question_id': g['id'], 'category': g['category'], 'status': row['status'],
                       'recall_at_5': len(correct) / len(required) if required else None,
                       'precision_at_5': len(correct) / len(got) if got and required else (0 if required else None),
                       'reciprocal_rank': reciprocal, 'all_required_sources': required <= set(got) if required else None,
                       'negative_empty': not hits if negative else None,
                       'obsolete_hit_count': sum('/note-040' in s['document_id'] and (s['document_id'], s['revision']) not in required for s in hits),
                       'cross_scope_hits': sum(not s['document_id'].startswith(f"{g['organization_id']}/{g['knowledge_space_id']}/") for s in hits)})
    positive = [s for s in scores if s['recall_at_5'] is not None]
    negatives = [s for s in scores if s['negative_empty'] is not None]
    return {'questions': len(scores), 'recall_at_5': fraction([s['recall_at_5'] for s in positive]),
            'precision_at_5': fraction([s['precision_at_5'] for s in positive]),
            'mrr_at_5': fraction([s['reciprocal_rank'] for s in positive]),
            'all_required_sources_rate': fraction([s['all_required_sources'] for s in positive]),
            'negative_empty_hit_rate': fraction([s['negative_empty'] for s in negatives]),
            'obsolete_hit_count': sum(s['obsolete_hit_count'] for s in scores),
            'cross_scope_hits': sum(s['cross_scope_hits'] for s in scores), 'scores': scores}


def parse_answer(raw):
    if isinstance(raw, dict): return raw
    raw = raw.strip()
    if raw.startswith('```'):
        raw = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw)
    return json.loads(raw)


def score_answer(answer, gold, corpus, observed_sources):
    """All components, exact revisions, scope and in-session observations required."""
    negative = bool(gold['abstain'])
    abstain = answer.get('abstain') is True
    required = {(s['document_id'], s['revision']) for s in gold['required_sources']}
    supplied = answer.get('citations', [])
    if not isinstance(supplied, list): supplied = []
    citations = set()
    invalid = []
    prefix = f"{gold['organization_id']}/{gold['knowledge_space_id']}/"
    for item in supplied:
        try:
            doc, rev = item['document_id'], item['revision']
            if not doc.startswith(prefix): raise PermissionError('foreign scope citation')
            verify_source_revision(corpus, gold['organization_id'], gold['knowledge_space_id'], doc, rev)
            if (doc, rev) not in observed_sources: raise ValueError('citation not observed in this session')
            citations.add((doc, rev))
        except (KeyError, TypeError, ValueError, PermissionError, FileNotFoundError) as exc:
            invalid.append(str(exc))
    text = normal(answer.get('answer', ''))
    components = [any(re.search(pattern, text) for pattern in alternatives) for alternatives in gold.get('answer_patterns', [])]
    components_correct = all(components) and bool(components) if not negative else abstain
    citation_complete = required <= citations and not invalid
    grounded = (abstain and not invalid) if negative else (not abstain and components_correct and citation_complete)
    return {'question_id': gold['id'], 'category': gold['category'], 'abstain_expected': negative,
            'abstain_observed': abstain, 'component_correct': components_correct,
            'component_checks': components, 'citation_complete': citation_complete,
            'citation_errors': invalid, 'strict_grounded_correct': grounded,
            'obsolete_citations': sum('/note-040' in doc and (doc, rev) not in required for doc, rev in citations)}


def main():
    p=argparse.ArgumentParser(); p.add_argument('--retrieval',type=Path,required=True); p.add_argument('--gold',type=Path,required=True); p.add_argument('--out',type=Path,required=True)
    a=p.parse_args(); a.out.write_text(json.dumps(score_retrieval(load_jsonl(a.retrieval),load_jsonl(a.gold)),ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__': main()
