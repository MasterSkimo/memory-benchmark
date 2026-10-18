"""Public V2 development notes only: no evaluation questions or gold answers.

The final questions are authored independently after implementation/model freeze.
All ten scopes have distinct values and explicit bilingual durable decisions.
"""
from __future__ import annotations
import json
from pathlib import Path


def create(root: Path):
    labels = ['Iris', 'Orion', 'Silex', 'Tilleul', 'Vega', 'Aster', 'Balsa', 'Cedar', 'Dune', 'Emeraude']
    recoveries = [
        ('file persistante sur disque', 'write commands to a durable disk queue'),
        ('disjoncteur applicatif', 'open the circuit and stop forwarding requests'),
        ('lecture seule', 'allow reads while rejecting every mutation'),
        ('service de secours', 'route traffic to the warm standby'),
        ('rejeu différé', 'defer processing and replay after upstream recovers'),
    ]
    actions = [
        ('rejeu idempotent', 'replay the journal without applying any operation twice'),
        ('reprise du curseur', 'resume from the last acknowledged cursor'),
        ('contrôle de somme', 'compare stored checksums before acknowledging recovery'),
        ('promotion du secours', 'promote the standby only after replication catches up'),
        ('relecture du journal', 'read the durable log in sequence before reopening traffic'),
    ]
    count = 0
    for org_index, org in enumerate(('org-alto', 'org-boreal')):
        for project_index in range(5):
            n = org_index * 5 + project_index
            project = f'project-{project_index+1:02d}'
            service = labels[n]
            runbook = f'PB-{service.upper()}'
            rpo = 8 + n * 7
            old_days = 14 + n * 2
            days = 63 + n * 11
            recovery_fr, recovery_en = recoveries[(n + org_index) % len(recoveries)]
            action_fr, action_en = actions[(n + 2) % len(actions)]
            owner = ('équipe Cobalt' if n % 2 == 0 else 'équipe Ambre')
            route = ('bascule progressive' if n % 2 == 0 else 'double exploitation vérifiée')
            bodies = {
                0: f'# Budget de perte — {service}\n\nPour {service}, la relève après sinistre peut perdre au maximum {rpo} minutes d’écritures validées. Ce budget concerne la fraîcheur des données restaurées, et non le temps de remise en service.\n',
                10: f'# Upstream outage — {service}\n\nIf the upstream supplier stops responding, {service} must {recovery_en}. The approved French shorthand is « {recovery_fr} ». Automatic retries with no durable record are forbidden.\n',
                20: f'# Acheminement — {service}\n\nLe relais {service} dépend du runbook {runbook}. La procédure terminale est décrite dans [[note-030]], pas dans ce document. The relay cannot reopen traffic until that playbook has finished.\n',
                30: f'# Final playbook step — {runbook}\n\nFor {runbook}, the last mandatory operation is: {action_en}. Le nom de cette action est « {action_fr} ». Le relais lié est décrit dans [[note-020]].\n',
                40: f'# Décision historique — archives {service}\n\nDécision valable du 2026-01-01 au 2026-04-30 : conserver les dossiers {old_days} jours. Cette politique est obsolète depuis le 2026-05-01 et remplacée par [[note-050]]. Ne pas l’appliquer aux décisions actuelles.\n',
                50: f'# Current records decision — {service}\n\nSigned on 2026-05-01: keep {service} records for {days} days, then purge them. This replaces the earlier {old_days}-day policy in [[note-040]]. The previous limit no longer authorizes deletion.\n',
                60: f'# Révision du déploiement — {service}\n\nVersion v2-r2, approuvée le 2026-07-15 : avant toute mise en production de {service}, obtenir la validation de l’{owner}, puis utiliser une {route}. La version v2-r1 demandait seulement une validation individuelle; cette ancienne règle est retirée. Current approval and rollout must both follow this revised instruction.\n',
                70: f'# Entretien documentaire — {service}\n\nLes index sont reconstruisibles depuis Markdown. Les journaux techniques temporaires sont hors périmètre. Aucun mot de passe, clé privée, code de coffre, salaire ou contrat commercial ne figure dans ces notes. A weekly documentation review checks broken links; it does not change recovery or records decisions.\n',
            }
            scope = root / org / project
            scope.mkdir(parents=True, exist_ok=True)
            for index, body in bodies.items():
                document_id = f'{org}/{project}/note-{index:03d}'
                revision = 'v2-r2' if index == 60 else f'v2-{n:02d}-{index:03d}'
                status = 'superseded' if index == 40 else 'active'
                date = '2026-01-01' if index == 40 else ('2026-05-01' if index == 50 else '2026-07-15' if index == 60 else '2026-01-01')
                metadata = f'---\ndocument_id: {document_id}\norganization_id: {org}\nknowledge_space_id: {project}\nrevision: {revision}\nstatus: {status}\nvalid_from: {date}\n'
                if index == 40:
                    metadata += 'valid_to: 2026-04-30\nsuperseded_by: note-050\n'
                (scope / f'note-{index:03d}.md').write_text(metadata + '---\n\n' + body, encoding='utf-8')
                count += 1
    return {'benchmark': 'BENCH-0002', 'corpus_version': 'v2-dev-1', 'seed': 20261018,
            'notes': count, 'organizations': 2, 'projects_per_organization': 5,
            'notes_per_scope': 8, 'languages': ['fr', 'en'],
            'evaluation_questions': 'NOT_GENERATED: independent author only after implementation freeze',
            'blindness': 'NON_BLIND_DEVELOPMENT: native workers share filesystem; no withheld-access boundary proven'}


if __name__ == '__main__':
    root = Path('fixtures/v2/vault')
    manifest = create(root)
    from benchkit.v2.integrity import corpus_digest
    manifest['corpus_sha256'] = corpus_digest(root)
    Path('fixtures/v2/corpus-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))
