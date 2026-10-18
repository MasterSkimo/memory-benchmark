"""Single-question retrieval entry point; invoke once per fresh question."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from scoped_vault import ScopedMarkdownVault


def run_one(question_record: dict, corpus_root: str | Path, top_k: int = 5) -> dict:
    vault = ScopedMarkdownVault(corpus_root,
                                question_record["organization_id"],
                                question_record["knowledge_space_id"])
    result = vault.search(question_record["question"], top_k=top_k)
    return {"candidate": "luna-vault-direct", "question_id": question_record.get("id", question_record.get("question_id")),
            "lane": "P1R", "status": "EXECUTED", "retrieved": result["hits"],
            "latency_ms": result["latency_ms"], "backend_calls": result["backend_calls"],
            "file_reads": result["file_reads"], "bytes_read": result["bytes_read"],
            "input_tokens": None, "output_tokens": None, "tool_calls": None}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python run_one.py CORPUS_ROOT < one-question.json")
    print(json.dumps(run_one(json.load(sys.stdin), sys.argv[1]), ensure_ascii=False))
