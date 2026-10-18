"""Integration test against Basic Memory's actual sync and FTS5 services."""
from pathlib import Path
import tempfile
import uuid
import unittest


class BasicMemoryIntegrationTest(unittest.TestCase):
    def test_roundtrip_scope_and_revision(self):
        with tempfile.TemporaryDirectory(prefix="bm-integration-") as tmp:
            root = Path(tmp)
            corpus = root / "vault"
            org_a = f"org-a-{uuid.uuid4().hex[:8]}"
            org_b = f"org-b-{uuid.uuid4().hex[:8]}"
            authorized = corpus / org_a / "space-a"
            foreign = corpus / org_b / "space-b"
            authorized.mkdir(parents=True)
            foreign.mkdir(parents=True)
            note = authorized / "evidence.md"
            note.write_text(
                f"---\ndocument_id: {org_a}/space-a/evidence\nrevision: r1\n"
                f"organization_id: {org_a}\nknowledge_space_id: space-a\n---\n"
                "# Evidence\nThe approved glacier protocol is amber-otter.\n",
                encoding="utf-8",
            )
            (foreign / "evidence.md").write_text(
                f"---\ndocument_id: {org_b}/space-b/evidence\nrevision: r1\n"
                f"organization_id: {org_b}\nknowledge_space_id: space-b\n---\n"
                "# Evidence\nForeign marker cobalt-lynx.\n",
                encoding="utf-8",
            )
            from adapter import create_adapter

            adapter = create_adapter(corpus, org_a, "space-a")
            q = {"question": "amber-otter", "organization_id": org_a, "knowledge_space_id": "space-a"}
            result = adapter.search(q, top_k=5)
            self.assertEqual([h["document_id"] for h in result["hits"]], [f"{org_a}/space-a/evidence"])
            self.assertEqual(result["hits"][0]["revision"], "r1")
            self.assertEqual(result["backend_calls"], 1)
            self.assertEqual(result["file_reads"], 1)
            self.assertGreater(result["bytes_read"], 0)
            with self.assertRaises(ValueError):
                adapter.search({"question": "amber-otter"}, 0)
            with self.assertRaises(PermissionError):
                adapter.search({"question": "amber-otter", "organization_id": org_b}, 5)

            foreign_adapter = create_adapter(corpus, org_b, "space-b")
            foreign_hit = foreign_adapter.search({"question": "cobalt-lynx"}, 5)["hits"]
            self.assertEqual([h["document_id"] for h in foreign_hit], [f"{org_b}/space-b/evidence"])
            self.assertEqual(foreign_hit[0]["revision"], "r1")
            self.assertEqual(adapter.search({"question": "cobalt-lynx"}, 5)["hits"], [])
            self.assertEqual(adapter.search(q, 5)["hits"][0]["document_id"], f"{org_a}/space-a/evidence")

            note.write_text(note.read_text(encoding="utf-8").replace("revision: r1", "revision: r2").replace("amber-otter", "silver-heron"), encoding="utf-8")
            updated = create_adapter(corpus, org_a, "space-a")
            revised = updated.search({"question": "silver-heron"}, 5)["hits"]
            self.assertEqual(revised[0]["revision"], "r2")
            self.assertEqual(updated.search({"question": "amber-otter"}, 5)["hits"], [])

    def test_rejects_missing_revision_and_forged_document_prefix(self):
        with tempfile.TemporaryDirectory(prefix="bm-invalid-") as tmp:
            corpus = Path(tmp) / "vault"
            scope = corpus / "org-a" / "space-a"
            scope.mkdir(parents=True)
            path = scope / "forged.md"
            path.write_text(
                "---\ndocument_id: org-b/space-b/forged\nrevision: r1\n"
                "organization_id: org-a\nknowledge_space_id: space-a\n---\n# Forged\n",
                encoding="utf-8",
            )
            from adapter import create_adapter
            with self.assertRaisesRegex(ValueError, "document_id"):
                create_adapter(corpus, "org-a", "space-a")
            path.write_text(
                "---\ndocument_id: org-a/space-a/forged\n"
                "organization_id: org-a\nknowledge_space_id: space-a\n---\n# Missing revision\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "revision"):
                create_adapter(corpus, "org-a", "space-a")


if __name__ == "__main__":
    unittest.main()
