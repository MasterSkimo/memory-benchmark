"""Check generated benchmark inputs without spending model tokens."""
from __future__ import annotations
import json
from pathlib import Path
def run(root:Path=Path("fixtures")) -> None:
    """Validate public fixture integrity and lack of answer oracle."""
    notes=list((root/"vault").rglob("*.md"))
    rows=[json.loads(x) for x in (root/"questions_public.jsonl").read_text().splitlines() if x]
    pilot=[json.loads(x) for x in (root/"questions_public_pilot.jsonl").read_text().splitlines() if x]
    assert len(notes)==1000 and len(rows)==200 and len(pilot)==20
    assert len(set(q["id"] for q in rows))==200
    assert all("expected_answer" not in q for q in rows)
    assert not (root/"private").exists()
    print("PASS: 1000 public notes, 200 questions, 20 pilot, no oracle")
if __name__=="__main__":run()
