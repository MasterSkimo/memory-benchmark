import tempfile
import unittest
from pathlib import Path

from adapter import create_adapter


class GraphitiNeo4jIntegrationTest(unittest.TestCase):
    """Requires the documented local Neo4j 5.26 service."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self._note("old.md", "acme/project-a/item", "acme", "project-a", "r1", "superseded", "Cobalt policy is old.")
        self._note("current.md", "acme/project-a/item", "acme", "project-a", "r2", "active", "Cobalt policy is current.")
        self._note("other.md", "acme/project-b/item", "acme", "project-b", "r1", "active", "Cobalt private project B.")
        self._note("tenant.md", "other/project-a/item", "other", "project-a", "r1", "active", "Cobalt private tenant.")
        self.adapter = create_adapter(self.root, "acme", "project-a")

    def tearDown(self):
        self.adapter.close()
        self.tmp.cleanup()

    def _note(self, filename, doc, org, space, revision, status, body):
        (self.root / filename).write_text(
            f"---\ndocument_id: {doc}\norganization_id: {org}\nknowledge_space_id: {space}\nrevision: {revision}\nstatus: {status}\n---\n\n{body}\n",
            encoding="utf-8",
        )

    def test_authorized_query_provenance_and_current_revision(self):
        result = self.adapter.search({"question": "Cobalt policy", "organization_id": "acme", "knowledge_space_id": "project-a"})
        self.assertEqual(len(result["hits"]), 1)
        self.assertEqual(result["hits"][0]["document_id"], "acme/project-a/item")
        self.assertEqual(result["hits"][0]["revision"], "r2")
        self.assertIn("current", result["hits"][0]["text"])

    def test_rejects_other_org_and_project_before_query(self):
        for org, space in (("other", "project-a"), ("acme", "project-b")):
            with self.assertRaises(PermissionError):
                self.adapter.search({"question": "Cobalt", "organization_id": org, "knowledge_space_id": space})

    def test_shared_backend_does_not_mix_foreign_scope(self):
        foreign = []
        for org, space, slug in (("other", "project-a", "foreign-org"), ("acme", "project-b", "foreign-project")):
            foreign_dir = self.root / slug
            foreign_dir.mkdir()
            (foreign_dir / "foreign.md").write_text(
                f"---\ndocument_id: {org}/{space}/{slug}\norganization_id: {org}\nknowledge_space_id: {space}\nrevision: r1\nstatus: active\n---\n\nCobalt secret from {slug}.\n",
                encoding="utf-8",
            )
            foreign.append((slug, create_adapter(foreign_dir, org, space)))
        try:
            for slug, adapter in foreign:
                foreign_hits = adapter.search({"question": "Cobalt secret"})["hits"]
                expected_prefix = "other/project-a/" if slug == "foreign-org" else "acme/project-b/"
                self.assertIn(f"{expected_prefix}{slug}", [h["document_id"] for h in foreign_hits])
                self.assertTrue(all(h["document_id"].startswith(expected_prefix) for h in foreign_hits))
            own_hits = self.adapter.search({"question": "Cobalt secret"})["hits"]
            self.assertFalse(any("foreign" in h["document_id"] for h in own_hits))
        finally:
            for _, adapter in foreign:
                adapter.close()

    def test_rejects_forged_document_prefix_and_missing_revision(self):
        forged = self.root / "forged.md"
        forged.write_text(
            "---\ndocument_id: other/project-a/forged\norganization_id: acme\nknowledge_space_id: project-a\nrevision: r1\n---\n\nCobalt forged.\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "prefix"):
            create_adapter([forged], "acme", "project-a")
        self.assertFalse(any(h["document_id"] == "other/project-a/forged"
                             for h in self.adapter.search({"question": "Cobalt forged"})["hits"]))
        missing_revision = self.root / "missing-revision.md"
        missing_revision.write_text(
            "---\ndocument_id: acme/project-a/no-revision\norganization_id: acme\nknowledge_space_id: project-a\n---\n\nCobalt no revision.\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "revision"):
            create_adapter([missing_revision], "acme", "project-a")

    def test_top_k_must_be_positive_integer(self):
        for value in (0, -1, 1.5, True):
            with self.assertRaises(ValueError):
                self.adapter.search({"question": "Cobalt"}, top_k=value)


if __name__ == "__main__":
    unittest.main()
