"""Native direct-candidate command launcher for the shared read-only answer API."""
from __future__ import annotations
import argparse, json, os, re, sys
from pathlib import Path

REPO_ROOT=Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path: sys.path.insert(0,str(REPO_ROOT))
from benchkit.v2.answer_tool import BoundAnswerTool
from scoped_vault import ScopedMarkdownVault

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--session-config",type=Path,required=True)
    args=parser.parse_args()
    token=os.environ.get("BENCH_SESSION_TOKEN")
    if not token: raise SystemExit("BENCH_SESSION_TOKEN must be supplied by the trusted session launcher")
    config=json.loads(args.session_config.read_text(encoding="utf-8"))
    question_id=config.get("question_id","")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}",question_id): raise SystemExit("invalid trusted question id")
    adapter=ScopedMarkdownVault(config["corpus_root"],config["organization_id"],config["knowledge_space_id"])
    events=Path(config.get("events_path",REPO_ROOT/"results/v2/luna-vault-direct/events"/f"{question_id}.jsonl"))
    tool=BoundAnswerTool(config,token,adapter,events_path=events)
    try:
        request=json.load(sys.stdin)
        print(json.dumps(tool.invoke(request),ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"error":f"{type(exc).__name__}: {exc}"}),file=sys.stderr)
        raise SystemExit(2)
if __name__=="__main__": main()
