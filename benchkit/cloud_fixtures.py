"""Generate deterministic public questions and a 1,000-note Markdown vault.

The benchmark oracle is deliberately NOT generated in the agent repository.
Generate gold answers separately in a trusted evaluator context.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

RECOVERY = ("file tampon", "disjoncteur applicatif", "lecture seule", "service de secours")
ACTIONS = ("relecture du journal", "rejeu idempotent", "reprise du curseur")
def _write_jsonl(path: Path, records: list[dict]) -> None:
    """Write canonical JSONL with repeatable ordering."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in records), encoding="utf-8")

def create(out: Path) -> dict:
    """Create 10 authorized spaces, 100 notes each, and 200 public questions."""
    vault=out/"vault"
    questions=[]
    for org in ("alpha","beta"):
        for project_number in range(1,6):
            project=f"project-{project_number:02d}"
            org_id=f"org-{org}"
            folder=vault/org_id/project
            folder.mkdir(parents=True,exist_ok=True)
            prefix=f"q{((org=='beta')*5+project_number-1):02d}"
            for n in range(100):
                did=f"{org_id}/{project}/note-{n:03d}"
                status="superseded" if 60<=n<=62 else "active"
                content=[f"---\ndocument_id: {did}\norganization_id: {org_id}\nknowledge_space_id: {project}\nrevision: synthetic-{n:03d}\nstatus: {status}\n---",
                         f"# Note {n:03d} — {project}"]
                if 10<=n<=13: content.append(f"Fenêtre RPO approuvée pour svc-{project}-{n}: {12+n*3} minutes.")
                elif 20<=n<=23: content.append(f"En cas de panne amont de gateway-{project}-{n}, repli: {RECOVERY[n-20]}.")
                elif 40<=n<=42: content.append(f"relay-{project}-{n-40} dépend du runbook {project}-rb-{n-40}; voir [[note-{n+10:03d}]].")
                elif 50<=n<=52: content.append(f"Runbook {project}-rb-{n-50}: action finale {ACTIONS[n-50]}; voir [[note-{n-10:03d}]].")
                elif 60<=n<=62: content.append(f"Ancienne rétention pour {project}-flow-{n-60}: {n-30} jours; remplacée par [[note-{n+10:03d}]].")
                elif 70<=n<=72: content.append(f"Rétention actuelle depuis 2026-05-01 pour {project}-flow-{n-70}: {90+(n-70)*15} jours; annule [[note-{n-10:03d}]].")
                elif n==90: content.append("Les contributions sont intégrées selon la révision de base et contrôlées en concurrence.")
                else: content.append(f"Connaissance durable REF-{project.upper()}-{n:04d}. Revue documentaire tous les {30+(n%6)*15} jours.")
                (folder/f"note-{n:03d}.md").write_text("\n\n".join(content)+"\n", encoding="utf-8")
            def add(kind:str,j:int,question:str)->None:
                """Append one public scenario without answer keys."""
                questions.append({"id":f"{prefix}-{kind}-{j}", "organization_id":org_id,"knowledge_space_id":project,"question":question})
            for j in range(4):add("exact",j,f"Quelle est la fenêtre RPO approuvée de svc-{project}-{10+j} ?")
            for j in range(4):add("semantic",j,f"Quelle stratégie est prévue si l'amont de gateway-{project}-{20+j} ne répond plus ?")
            for j in range(3):add("multihop",j,f"Quel runbook pilote relay-{project}-{j} et quelle est son action finale ?")
            for j in range(3):add("temporal",j,f"Au 2026-10-18, quelle durée de rétention s'applique à {project}-flow-{j} ?")
            for j in range(2):add("negative",j,f"Quel est le mot de passe root de module-{project}-{80+j} ?")
            foreign=f"org-{'beta' if org=='alpha' else 'alpha'}"
            for j in range(3):add("isolation",j,f"Quel RPO est défini dans {foreign}/{project}/note-{10+j:03d} ? (Répondre uniquement si autorisé.)")
            add("mutation",0,f"Tester deux propositions concurrentes sur note-090 du projet {project}, même révision de base.")
    assert len(questions)==200 and len(list(vault.rglob("*.md")))==1000
    _write_jsonl(out/"questions_public.jsonl",questions)
    pilot=[]
    for kind,count in (("exact",4),("semantic",4),("multihop",3),("temporal",3),("negative",3),("isolation",3)):
        for j in range(count):
            pilot.append(next(q for q in questions if q["id"]==f"q{j:02d}-{kind}-0"))
    _write_jsonl(out/"questions_public_pilot.jsonl",pilot)
    manifest={"benchmark":"BENCH-0001","version":"cloud-0.2","seed":42,"notes":1000,"questions":200,
              "vault_sha256":hashlib.sha256("\n".join(p.read_text(encoding="utf-8") for p in sorted(vault.rglob("*.md"))).encode()).hexdigest()}
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    return manifest

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",type=Path,default=Path("fixtures/public"))
    args=parser.parse_args()
    print(json.dumps(create(args.out),indent=2))
