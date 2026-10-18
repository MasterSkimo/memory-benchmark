"""Real embedded-Qdrant integration and boundary tests; vectors are test doubles only."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "implementations/v2/common-models"))
sys.path.insert(0, str(Path(__file__).parent))

from adapter import QdrantMarkdownAdapter  # noqa: E402
from qdrant_client import models  # noqa: E402


class _TestEncoder:
    dimension = 384

    def __init__(self):
        self.calls = 0

    def token_count(self, text):
        return len(text.split())

    def encode(self, texts):
        self.calls += 1
        # Stable fixture vectors exercise actual dense+sparse Qdrant RRF plumbing.
        out = []
        for text in texts:
            v = [0.0] * self.dimension
            if "contrat" in text.casefold() or "contract" in text.casefold():
                v[0] = 1.0
            else:
                v[1] = 1.0
            out.append(v)
        return out


def _note(path: Path, docid: str, org: str, space: str, revision: str, body: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\ndocument_id: {docid}\norganization_id: {org}\nknowledge_space_id: {space}\nrevision: {revision}\n---\n\n{body}\n", encoding="utf-8")


def test_real_qdrant_dense_sparse_scope_provenance_and_counters(tmp_path):
    _note(tmp_path / "org-a" / "space-a" / "a.md", "org-a/space-a/a", "org-a", "space-a", "rev-2", "Contrat signé en mars")
    _note(tmp_path / "org-a" / "space-b" / "b.md", "org-a/space-b/b", "org-a", "space-b", "rev-1", "Contrat du projet voisin")
    _note(tmp_path / "org-b" / "space-a" / "c.md", "org-b/space-a/c", "org-b", "space-a", "rev-1", "Contrat autre organisation")
    adapter = QdrantMarkdownAdapter(tmp_path, "org-a", "space-a", embedder=_TestEncoder())
    try:
        result = adapter.search({"question": "Quel contrat a été signé?"}, top_k=5)
        assert [h["document_id"] for h in result["hits"]] == ["org-a/space-a/a"]
        assert result["hits"][0]["revision"] == "rev-2"
        assert result["backend_calls"] == 1 and result["file_reads"] == 0
        assert adapter.ingest_file_reads == 1 and adapter.ingest_backend_calls == 1
        assert adapter.ingest_embedding_calls == 1 and adapter.ingest_embedding_tokens > 0
        assert result["embedding_calls"] == 1 and result["embedding_tokens"] == 5
        for forged in [
            {"question": "contrat", "organization_id": "org-b"},
            {"question": "contrat", "knowledge_space_id": "space-b"},
        ]:
            try:
                adapter.search(forged)
            except PermissionError:
                pass
            else:
                raise AssertionError("forged scope was accepted")
        for override in ({"question": "contrat", "document_id": "org-b/space-a/c"},
                         {"question": "contrat", "path": "../../org-b/space-a/c.md"},
                         {"question": "contrat", "tenant_filter": {"organization_id": "org-b"}}):
            try:
                adapter.search(override)
            except PermissionError:
                pass
            else:
                raise AssertionError("forged path or tenant filter was accepted")
        try:
            adapter.search({"question": "contrat", "revision": "rev-1"})
        except PermissionError:
            pass
        else:
            raise AssertionError("stale revision override was accepted")
    finally:
        adapter.close()


def test_rejects_forged_document_metadata_and_traversal(tmp_path):
    bad = tmp_path / "org-a" / "space-a" / "bad.md"
    _note(bad, "org-a/space-a/forged", "org-a", "space-a", "rev-1", "forged")
    try:
        QdrantMarkdownAdapter(bad, "org-a", "space-a", embedder=_TestEncoder())
    except ValueError:
        pass
    else:
        raise AssertionError("inconsistent document metadata was accepted")

    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.md"
    _note(outside, "org-a/space-a/outside", "org-a", "space-a", "rev-1", "outside")
    (root / "escape.md").symlink_to(outside)
    try:
        QdrantMarkdownAdapter(root, "org-a", "space-a", embedder=_TestEncoder())
    except ValueError:
        pass
    else:
        raise AssertionError("symlink traversal was accepted")


def test_neural_encoder_runs_crosslingual_local_qdrant(tmp_path):
    # Development smoke evidence only; this pair is not from the benchmark questions.
    _note(tmp_path / "org-a" / "space-a" / "agreement.md", "org-a/space-a/agreement", "org-a", "space-a", "rev-current", "le client a demandé une prolongation du contrat")
    adapter = QdrantMarkdownAdapter(tmp_path, "org-a", "space-a")
    try:
        result = adapter.search({"question": "the client asked for a contract extension"}, top_k=1)
        assert len(result["hits"]) == 1
        assert result["hits"][0]["document_id"] == "org-a/space-a/agreement"
        assert result["hits"][0]["revision"] == "rev-current"
        assert result["backend_calls"] == 1
    finally:
        adapter.close()


def test_superseded_revision_is_not_indexed(tmp_path):
    old = tmp_path / "org-a" / "space-a" / "decision-old.md"
    current = tmp_path / "org-a" / "space-a" / "decision.md"
    _note(old, "org-a/space-a/decision-old", "org-a", "space-a", "rev-1", "the service uses the old database")
    old.write_text(old.read_text().replace("revision: rev-1\n", "revision: rev-1\nstatus: superseded\n"), encoding="utf-8")
    _note(current, "org-a/space-a/decision", "org-a", "space-a", "rev-2", "the service uses the current database")
    adapter = QdrantMarkdownAdapter(tmp_path, "org-a", "space-a", embedder=_TestEncoder())
    try:
        hits = adapter.search({"question": "current database"})["hits"]
        assert len(hits) == 1 and hits[0]["revision"] == "rev-2"
        assert "current" in hits[0]["text"]
    finally:
        adapter.close()


def test_foreign_path_cannot_forge_trusted_scope_and_is_not_read(tmp_path):
    foreign = tmp_path / "org-b" / "space-b" / "forged.md"
    _note(foreign, "org-a/space-a/forged", "org-a", "space-a", "rev-1", "forged in another project")
    adapter = QdrantMarkdownAdapter(tmp_path, "org-a", "space-a", embedder=_TestEncoder())
    try:
        assert adapter.ingest_file_reads == 0
        assert adapter.ingest_embedding_calls == 0
        assert adapter.search({"question": "forged project"})["hits"] == []
    finally:
        adapter.close()


def test_rejects_malformed_trusted_scope(tmp_path):
    try:
        QdrantMarkdownAdapter(tmp_path, "org-a/../org-b", "space-a", embedder=_TestEncoder())
    except ValueError:
        pass
    else:
        raise AssertionError("malformed trusted scope was accepted")


def test_mapping_drops_forged_backend_document_metadata(tmp_path):
    _note(tmp_path / "org-a" / "space-a" / "valid.md", "org-a/space-a/valid", "org-a", "space-a", "rev-1", "contract record")
    adapter = QdrantMarkdownAdapter(tmp_path, "org-a", "space-a", embedder=_TestEncoder())
    try:
        adapter.client.upsert(adapter.collection, points=[models.PointStruct(
            id="00000000-0000-0000-0000-000000000001",
            vector={"dense": [1.0] + [0.0] * 383, "sparse": models.SparseVector(indices=[12], values=[1.0])},
            payload={"organization_id": "org-a", "knowledge_space_id": "space-a",
                     "document_id": "org-b/space-a/forged", "revision": "rev-forged", "text": "forged"},
        )], wait=True)
        hits = adapter.search({"question": "contract record"})["hits"]
        assert hits and all(hit["document_id"].startswith("org-a/space-a/") for hit in hits)
        assert all(hit["document_id"] != "org-b/space-a/forged" for hit in hits)
    finally:
        adapter.close()
