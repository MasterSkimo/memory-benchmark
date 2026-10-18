import tempfile
import unittest
from pathlib import Path

from qdrant_client import QdrantClient, models

from adapter import QdrantMarkdownAdapter


def write_note(root, name, doc, org, space, revision, body):
    p = root / name
    p.write_text(f"---\ndocument_id: {doc}\norganization_id: {org}\nknowledge_space_id: {space}\nrevision: {revision}\n---\n\n{body}\n", encoding="utf-8")
    return p


class QdrantAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.a = write_note(self.root, "a.md", "acme/p1/a", "acme", "p1", "r1", "cobalt beacon policy reference")
        self.b = write_note(self.root, "b.md", "acme/p1/b", "acme", "p1", "r1", "amber report logistics")
        self.other = write_note(self.root, "other.md", "acme/p2/secret", "acme", "p2", "r1", "cobalt secret tenant")
        self.org_other = write_note(self.root, "org.md", "other/p1/secret", "other", "p1", "r1", "cobalt secret org")
        self.client = QdrantClient(":memory:")
        self.adapter = QdrantMarkdownAdapter([self.a, self.b, self.other, self.org_other], "acme", "p1", client=self.client, collection="test")

    def tearDown(self):
        self.client.close()
        self.tmp.cleanup()

    def test_dense_sparse_and_rrf_queries_are_indexed_and_scoped(self):
        scope = models.Filter(must=[
            models.FieldCondition(key="organization_id", match=models.MatchValue(value="acme")),
            models.FieldCondition(key="knowledge_space_id", match=models.MatchValue(value="p1")),
        ])
        dense, sparse = self.adapter.__class__.__module__, None
        from adapter import _vectors
        dv, sv = _vectors("cobalt beacon")
        dense_hits = self.client.query_points("test", query=dv, using="dense", query_filter=scope, limit=5).points
        sparse_hits = self.client.query_points("test", query=sv, using="sparse", query_filter=scope, limit=5).points
        self.assertTrue(dense_hits)
        self.assertTrue(sparse_hits)
        result = self.adapter.search({"question": "cobalt beacon"}, top_k=5)
        self.assertEqual(result["hits"][0]["document_id"], "acme/p1/a")
        self.assertTrue(all(h["document_id"].startswith("acme/p1/") for h in result["hits"]))

    def test_constructor_scope_rejects_org_and_project_tampering(self):
        for query in ({"question": "cobalt", "organization_id": "other", "knowledge_space_id": "p1"},
                      {"question": "cobalt", "organization_id": "acme", "knowledge_space_id": "p2"}):
            with self.assertRaises(PermissionError):
                self.adapter.search(query)

    def test_revision_update_replaces_current_document_and_returns_citation(self):
        write_note(self.root, "a.md", "acme/p1/a", "acme", "p1", "r2", "cobalt beacon revised protocol")
        self.adapter.ingest([self.a])
        hit = self.adapter.search({"question": "revised protocol"})["hits"][0]
        self.assertEqual((hit["document_id"], hit["revision"]), ("acme/p1/a", "r2"))
        self.assertIn("revised protocol", hit["text"])

    def test_ingestion_rejects_forged_document_id_scope(self):
        forged = write_note(self.root, "forged.md", "other/p1/forged", "acme", "p1", "r1", "forged content")
        with self.assertRaisesRegex(ValueError, "document_id must begin"):
            QdrantMarkdownAdapter([forged], "acme", "p1", collection="forged-test")

    def test_ingestion_rejects_empty_scope_metadata(self):
        empty = self.root / "empty.md"
        empty.write_text("---\ndocument_id: acme/p1/empty\norganization_id: acme\nknowledge_space_id: \nrevision: r1\n---\nbody\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Missing knowledge_space_id"):
            QdrantMarkdownAdapter([empty], "acme", "p1", collection="empty-test")

    def test_search_rejects_invalid_top_k(self):
        for value in (0, -1, 1.5, True, "5"):
            with self.subTest(top_k=value), self.assertRaises(ValueError):
                self.adapter.search({"question": "cobalt"}, top_k=value)


if __name__ == "__main__":
    unittest.main()
