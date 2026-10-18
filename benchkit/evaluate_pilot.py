"""Evaluate closed pilot traces separately from candidate execution.

This is transparent synthetic development scoring, not a withheld evaluation.
Never run the evaluator while constructing candidate answers or retrieval logic.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re


def normalize(value):
    return ' '.join(str(value).casefold().split())


def source_catalog(corpus: Path):
    catalog = {}
    for path in sorted(corpus.rglob('*.md')):
        header = path.read_text().split('---', 2)[1]
        metadata = dict(line.split(':', 1) for line in header.splitlines() if ':' in line)
        metadata = {key.strip(): value.strip() for key, value in metadata.items()}
        catalog[metadata['document_id']] = metadata
    return catalog


def grade_answer(record, gold, catalog):
    """Missing observations never become successful abstentions."""
    if record is None or record.get('status') not in ('ok', 'ANSWER_TESTED', 'completed'):
        return {'observed': False, 'strict_match': False, 'value_match': False,
                'grounded_correct': False, 'leaks': 0, 'revision_errors': 0}
    answer = record.get('answer')
    citations = record.get('citations') or []
    prefix = gold['organization_id'] + '/' + gold['knowledge_space_id'] + '/'
    docs = {c.get('document_id') for c in citations}
    leaks = sum(not str(c.get('document_id', '')).startswith(prefix) for c in citations)
    revision_errors = sum(c.get('document_id') not in catalog or
        c.get('revision') != catalog.get(c.get('document_id'), {}).get('revision') for c in citations)
    if gold['should_abstain']:
        matched = answer is None or str(answer).strip() == ''
        return {'observed': True, 'strict_match': matched, 'value_match': matched,
                'grounded_correct': matched and not citations and not leaks,
                'leaks': leaks, 'revision_errors': revision_errors}
    canonical = gold['expected_answer']
    strict = normalize(answer) == normalize(canonical)
    # A declared component-containment measure complements strict string equality
    # for natural-language answers; it is not a human semantic judgment.
    parts = canonical.split(' ; ')
    value = all(normalize(part) in normalize(answer) for part in parts)
    supported = set(gold['supporting_document_ids']).issubset(docs)
    return {'observed': True, 'strict_match': strict, 'value_match': value,
            'grounded_correct': value and supported and not leaks and not revision_errors,
            'leaks': leaks, 'revision_errors': revision_errors}


def evaluate(candidate: str, root: Path):
    # Only the evaluator imports this public scoring algorithm, after traces close.
    from benchkit.trusted_evaluator import expected
    questions = [json.loads(x) for x in
                 (root / 'fixtures/questions_public_pilot.jsonl').read_text().splitlines()]
    gold = {q['id']: expected(q) for q in questions}
    catalog = source_catalog(root / 'fixtures/vault')
    folder = root / 'results' / candidate
    result = {'candidate': candidate, 'scope': 'open synthetic pilot, not blind',
              'policy': 'results/evaluation-policy.json'}
    retrieval = folder / 'retrieval.jsonl'
    if retrieval.exists():
        rows = [json.loads(line) for line in retrieval.read_text().splitlines() if line]
        assert len(rows) == 20 and {r['question_id'] for r in rows} == set(gold), 'Incomplete/duplicate R trace set'
        recalls, precisions, complete = [], [], []
        leaks = revision_errors = stale = empty_negative = 0
        for row in rows:
            g = gold[row['question_id']]
            hits = row.get('hits') or []
            ids = {h['document_id'] for h in hits}
            required = set(g['supporting_document_ids'])
            if required:
                overlap = len(ids & required)
                recalls.append(overlap / len(required))
                precisions.append(overlap / 5)
                complete.append(required.issubset(ids))
            else:
                empty_negative += int(not hits and row.get('status') == 'ok')
            prefix = g['organization_id'] + '/' + g['knowledge_space_id'] + '/'
            for hit in hits:
                leaks += int(not hit['document_id'].startswith(prefix))
                meta = catalog.get(hit['document_id'], {})
                revision_errors += int(not meta or hit.get('revision') != meta.get('revision'))
                stale += int(meta.get('status') == 'superseded')
        result['retrieval'] = {
            'observed_queries': len(rows), 'support_bearing_questions': len(recalls),
            'macro_recall_at_5': sum(recalls) / len(recalls),
            'macro_precision_at_5': sum(precisions) / len(precisions),
            'all_required_sources_fraction': sum(complete) / len(complete),
            'out_of_scope_hits': leaks, 'revision_mismatches': revision_errors,
            'superseded_hits': stale, 'empty_negative_or_isolation_queries': empty_negative,
            'negative_or_isolation_queries': 6,
            'trace_sha256': hashlib.sha256(retrieval.read_bytes()).hexdigest(),
        }
    answers = folder / 'end_to_end.jsonl'
    if answers.exists():
        rows = [json.loads(line) for line in answers.read_text().splitlines() if line]
        assert len({r['question_id'] for r in rows}) == len(rows), 'Duplicate E question'
        assert set(r['question_id'] for r in rows).issubset(gold), 'Non-pilot E question'
        observed = {r['question_id']: r for r in rows}
        grades = [grade_answer(observed.get(qid), g, catalog) for qid, g in gold.items()]
        result['answers'] = {
            'observed_sessions': sum(g['observed'] for g in grades), 'planned_questions': 20,
            'strict_string_match_fraction': sum(g['strict_match'] for g in grades) / 20,
            'canonical_component_match_fraction': sum(g['value_match'] for g in grades) / 20,
            'grounded_component_correct_fraction': sum(g['grounded_correct'] for g in grades) / 20,
            'out_of_scope_citations': sum(g['leaks'] for g in grades),
            'revision_mismatches': sum(g['revision_errors'] for g in grades),
            'verified_token_observations': sum(all((r.get('usage') or {}).get(k) is not None
                for k in ('input_tokens', 'cached_input_tokens', 'output_tokens')) for r in rows),
            'trace_sha256': hashlib.sha256(answers.read_bytes()).hexdigest(),
        }
    (folder / 'score.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--root', type=Path, default=Path('.'))
    args = parser.parse_args()
    print(json.dumps(evaluate(args.candidate, args.root), indent=2))


if __name__ == '__main__':
    main()
