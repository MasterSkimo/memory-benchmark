"""Audited, question-bound list/read/search tool for native answer sessions.

One JSON operation is sent on stdin per invocation. The session prompt should
provide only this command for its authorized question and scope.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

from scoped_vault import ScopeError, ScopedMarkdownVault

DEFAULT_CORPUS = Path(__file__).resolve().parents[2] / "fixtures" / "vault"
DEFAULT_EVENTS = Path(__file__).resolve().parents[2] / "results" / "luna-vault-direct" / "events"
MAX_CALLS = 12


def _audit_path(root: Path, question_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", question_id):
        raise ValueError("invalid question id")
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{question_id}.jsonl"


def invoke(operation: dict, *, corpus_root: str | Path, organization_id: str,
           knowledge_space_id: str, question_id: str,
           events_root: str | Path = DEFAULT_EVENTS) -> dict:
    if not isinstance(operation, dict) or operation.get("op") not in ("list", "read", "search"):
        raise ValueError("operation must be list, read, or search")
    audit_path = _audit_path(Path(events_root), question_id)
    previous = audit_path.read_text(encoding="utf-8").splitlines() if audit_path.exists() else []
    if len(previous) >= MAX_CALLS:
        raise RuntimeError(f"question reached {MAX_CALLS} tool calls")

    vault = ScopedMarkdownVault(corpus_root, organization_id, knowledge_space_id)
    before_reads = vault.counters.read_calls
    before_bytes = vault.counters.bytes_read
    started = time.perf_counter()
    error = None
    result = None
    try:
        op = operation["op"]
        if op == "list":
            result = vault.list_markdown()
            source_ids = [f"{organization_id}/{knowledge_space_id}/{path[:-3]}" for path in result]
        elif op == "read":
            result = vault.read_markdown(operation.get("document_id"))
            source_ids = [result["document_id"]]
        else:
            result = vault.search(operation.get("question"), top_k=operation.get("top_k", 5))
            source_ids = sorted({hit["document_id"] for hit in result["hits"]})
        status = "OK"
    except Exception as exc:
        status = "ERROR"
        error = f"{type(exc).__name__}: {exc}"
        source_ids = list(vault.counters.source_ids_read or [])
    elapsed_ms = (time.perf_counter() - started) * 1000
    event = {
        "question_id": question_id,
        "operation": operation.get("op"),
        "status": status,
        "latency_ms": elapsed_ms,
        "file_reads": vault.counters.read_calls - before_reads,
        "bytes_read": vault.counters.bytes_read - before_bytes,
        "source_ids": source_ids,
    }
    if error:
        event["error"] = error
    with audit_path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + "\n")
    if status != "OK":
        return {"error": error, "audit": event}
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--organization-id", required=True)
    parser.add_argument("--knowledge-space-id", required=True)
    parser.add_argument("--question-id", required=True)
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--events-root", type=Path, default=DEFAULT_EVENTS)
    args = parser.parse_args()
    try:
        operation = json.load(sys.stdin)
        result = invoke(operation, corpus_root=args.corpus_root,
                        organization_id=args.organization_id,
                        knowledge_space_id=args.knowledge_space_id,
                        question_id=args.question_id, events_root=args.events_root)
        print(json.dumps(result, ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}), file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
