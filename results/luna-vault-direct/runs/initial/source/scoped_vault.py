"""Filesystem-only Markdown access scoped to one organization and project.

No index is built. ``search`` performs a bounded lexical scan at call time and
is a tool implementation, not an answer model or a Luna substitute.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import time
from typing import Any


class ScopeError(PermissionError):
    """The request identity or source path falls outside the fixed scope."""


def _component(value: str, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", value):
        raise ScopeError(f"invalid {label}")
    return value


def _frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end < 0:
        return {}
    values: dict[str, str] = {}
    for line in text[4:end].splitlines():
        key, sep, value = line.partition(":")
        if sep:
            values[key.strip()] = value.strip().strip("\"'")
    return values


@dataclass
class VaultCounters:
    list_calls: int = 0
    read_calls: int = 0
    search_calls: int = 0
    bytes_read: int = 0
    source_ids_read: list[str] | None = None

    def __post_init__(self) -> None:
        if self.source_ids_read is None:
            self.source_ids_read = []


class ScopedMarkdownVault:
    """A native-file-tool surface fixed to one authorized org/project.

    ``corpus_root`` is the directory containing organization directories.
    The caller cannot switch identity per operation: constructor identity is
    mandatory, and optional request identities must exactly match it.
    """

    def __init__(self, corpus_root: str | Path, organization_id: str,
                 knowledge_space_id: str):
        self.organization_id = _component(organization_id, "organization_id")
        self.knowledge_space_id = _component(knowledge_space_id, "knowledge_space_id")
        self.corpus_root = Path(corpus_root).resolve(strict=True)
        if not self.corpus_root.is_dir():
            raise ValueError("corpus_root must be a directory")
        self.scope_root = self.corpus_root / self.organization_id / self.knowledge_space_id
        # Reject symlinked scope components, even when they point back inside.
        for component in (self.corpus_root / self.organization_id, self.scope_root):
            if component.is_symlink():
                raise ScopeError("symlinked scope directory")
        if not self.scope_root.is_dir():
            raise ScopeError("authorized scope does not exist")
        self.scope_real = self.scope_root.resolve(strict=True)
        self.counters = VaultCounters()

    def _authorize(self, organization_id: str | None, knowledge_space_id: str | None) -> None:
        if organization_id is not None and organization_id != self.organization_id:
            raise ScopeError("organization identity mismatch")
        if knowledge_space_id is not None and knowledge_space_id != self.knowledge_space_id:
            raise ScopeError("knowledge-space identity mismatch")

    def _relative_file(self, document_id: str) -> Path:
        if not isinstance(document_id, str) or not document_id or "\\" in document_id:
            raise ScopeError("invalid document identifier")
        # Accept scope-relative paths or canonical fixture IDs, with or without
        # the Markdown suffix used by the on-disk file.
        prefix = f"{self.organization_id}/{self.knowledge_space_id}/"
        if document_id.startswith(prefix):
            document_id = document_id[len(prefix):]
        elif "/" in document_id and not document_id.endswith(".md"):
            # A slash-containing extensionless identifier is canonical-looking;
            # do not reinterpret a foreign tenant/project as a nested path.
            first, _, remainder = document_id.partition("/")
            if first.startswith("org-") or remainder.startswith("project-"):
                raise ScopeError("canonical document identity mismatch")
        if not document_id.lower().endswith(".md"):
            document_id += ".md"
        rel = Path(document_id)
        if rel.is_absolute() or any(part in ("", ".", "..") for part in rel.parts):
            raise ScopeError("path traversal rejected")
        if rel.suffix.lower() != ".md":
            raise ScopeError("only Markdown sources are accessible")
        candidate = self.scope_root / rel
        cursor = self.scope_root
        for part in rel.parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise ScopeError("symlinked path component rejected")
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(self.scope_real)
        except (OSError, ValueError) as exc:
            raise ScopeError("source is outside authorized scope") from exc
        if not resolved.is_file() or resolved.suffix.lower() != ".md":
            raise ScopeError("source is not a Markdown file")
        return resolved

    def list_markdown(self, *, organization_id: str | None = None,
                      knowledge_space_id: str | None = None) -> list[str]:
        self._authorize(organization_id, knowledge_space_id)
        self.counters.list_calls += 1
        items: list[str] = []
        # Walk without following directory symlinks; verify each file again.
        for parent, dirs, files in __import__("os").walk(self.scope_root, followlinks=False):
            dirs[:] = [d for d in dirs if not (Path(parent) / d).is_symlink()]
            for name in files:
                if not name.endswith(".md"):
                    continue
                path = Path(parent) / name
                if path.is_symlink():
                    continue
                try:
                    path.resolve(strict=True).relative_to(self.scope_real)
                except (OSError, ValueError):
                    continue
                items.append(path.relative_to(self.scope_root).as_posix())
        return sorted(items)

    def read_markdown(self, document_id: str, *, organization_id: str | None = None,
                      knowledge_space_id: str | None = None) -> dict[str, Any]:
        self._authorize(organization_id, knowledge_space_id)
        path = self._relative_file(document_id)
        data = path.read_bytes()
        self.counters.read_calls += 1
        self.counters.bytes_read += len(data)
        text = data.decode("utf-8")
        meta = _frontmatter(text)
        rel = path.relative_to(self.scope_root).as_posix()
        expected_doc_id = f"{self.organization_id}/{self.knowledge_space_id}/{rel[:-3]}"
        doc_id = meta.get("document_id", expected_doc_id)
        # Metadata cannot relabel a source into a different tenant/project.
        if meta.get("organization_id", self.organization_id) != self.organization_id:
            raise ScopeError("source organization metadata mismatch")
        if meta.get("knowledge_space_id", self.knowledge_space_id) != self.knowledge_space_id:
            raise ScopeError("source knowledge-space metadata mismatch")
        if doc_id != expected_doc_id:
            raise ScopeError("source document_id metadata mismatch")
        self.counters.source_ids_read.append(doc_id)
        return {"document_id": doc_id, "revision": meta.get("revision"),
                "text": text, "path": rel}

    def search(self, question: str, *, top_k: int = 5,
               organization_id: str | None = None,
               knowledge_space_id: str | None = None) -> dict[str, Any]:
        """Lexically scan scoped Markdown at runtime and return provenance hits.

        This deterministic tool exists for the retrieval lane and smoke tests.
        It does not model Luna and must not be reported as Luna end-to-end.
        """
        self._authorize(organization_id, knowledge_space_id)
        if not isinstance(question, str) or not question.strip():
            raise ValueError("question must be non-empty text")
        if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 1 or top_k > 100:
            raise ValueError("top_k must be between 1 and 100")
        started = time.perf_counter()
        self.counters.search_calls += 1
        terms = {t.casefold() for t in re.findall(r"[\w-]+", question) if len(t) > 1}
        hits = []
        for rel in self.list_markdown():
            item = self.read_markdown(rel)
            body = item["text"].casefold()
            matched = sum(1 for term in terms if term in body)
            if matched:
                hits.append({"document_id": item["document_id"], "revision": item["revision"],
                             "score": matched / max(len(terms), 1), "text": item["text"]})
        hits.sort(key=lambda hit: (-hit["score"], hit["document_id"]))
        return {"hits": hits[:top_k], "latency_ms": (time.perf_counter() - started) * 1000,
                "backend_calls": None, "file_reads": self.counters.read_calls,
                "bytes_read": self.counters.bytes_read}
