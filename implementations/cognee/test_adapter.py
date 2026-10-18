"""Cognee adapter checks; full backend test runs when tokenizer/model prerequisites exist."""
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from adapter import (_explicit_local_inference_configured, _is_loopback_endpoint,
                     _metadata, create_adapter)


class ProvenanceTests(unittest.TestCase):
    def test_frontmatter_provenance_fields_are_preserved(self):
        fields = _metadata("---\ndocument_id: org-a/space-a/doc-1\nrevision: rev-7\n---\n# note\n")
        self.assertEqual(fields["document_id"], "org-a/space-a/doc-1")
        self.assertEqual(fields["revision"], "rev-7")

    def test_scope_mismatch_in_document_id_is_rejected_before_cognee(self):
        with tempfile.TemporaryDirectory(prefix="cognee-scope-") as temp:
            scoped = Path(temp) / "org-a" / "space-a"
            scoped.mkdir(parents=True)
            (scoped / "bad.md").write_text(
                "---\ndocument_id: org-a/space-b/doc-9\norganization_id: org-a\n"
                "knowledge_space_id: space-a\nrevision: rev-9\n---\nsecret\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "outside its authorized"):
                create_adapter(Path(temp), "org-a", "space-a")

    def test_local_inference_requires_opt_in_and_both_loopback_endpoints(self):
        llm = SimpleNamespace(llm_provider="ollama", llm_endpoint="http://127.0.0.1:11434",
                              structured_output_framework="instructor", fallback_endpoint="",
                              baml_llm_endpoint="")
        embedding = SimpleNamespace(embedding_provider="ollama",
                                    embedding_endpoint="http://localhost:11434")
        with patch.dict("os.environ", {"COGNEE_LOCAL_INFERENCE_OPT_IN": "1"}):
            self.assertTrue(_explicit_local_inference_configured(llm, embedding))
            self.assertFalse(_explicit_local_inference_configured(llm, SimpleNamespace(
                embedding_provider="ollama", embedding_endpoint="https://embeddings.example/api")))
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(_explicit_local_inference_configured(llm, embedding))
        self.assertFalse(_is_loopback_endpoint("https://user:pass@127.0.0.1:11434"))


class CogneeIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="cognee-integration-")
        cls.root = Path(cls.temp.name)
        scoped = cls.root / "org-a" / "space-a"
        scoped.mkdir(parents=True)
        (scoped / "doc-1.md").write_text(
            "---\ndocument_id: org-a/space-a/doc-1\norganization_id: org-a\n"
            "knowledge_space_id: space-a\nrevision: rev-7\n---\n"
            "# Operations\nThe test system keeps the documented revision.\n",
            encoding="utf-8",
        )
        other = cls.root / "org-a" / "space-b"
        other.mkdir(parents=True)
        (other / "doc-2.md").write_text(
            "---\ndocument_id: org-a/space-b/doc-2\norganization_id: org-a\n"
            "knowledge_space_id: space-b\nrevision: rev-1\n---\nsecret other project\n",
            encoding="utf-8",
        )
        cls.adapter = create_adapter(cls.root, "org-a", "space-a")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_constructor_reads_only_authorized_project_and_records_revisions(self):
        self.assertEqual(set(self.adapter._sources), {"org-a/space-a/doc-1"})
        self.assertEqual(self.adapter._sources["org-a/space-a/doc-1"]["revision"], "rev-7")
        self.assertEqual(self.adapter.ingest_file_reads, 1)
        self.assertEqual(self.adapter.ingestion_status in {"COMPLETED", "BLOCKED"}, True)

    def test_cross_project_and_cross_org_queries_rejected_before_retrieval(self):
        for org, space in (("org-b", "space-a"), ("org-a", "space-b")):
            with self.assertRaises(PermissionError):
                self.adapter.search({"organization_id": org, "knowledge_space_id": space,
                                     "question": "private data"}, 5)

    def test_real_cognee_vector_retrieval_when_ingestion_available(self):
        if self.adapter.ingestion_status != "COMPLETED":
            self.skipTest(self.adapter.ingestion_error or "Cognee ingestion unavailable")
        if self.adapter.extraction_status != "COMPLETED_LOCAL_OLLAMA":
            self.skipTest("Model-assisted Cognee cognify is blocked without local Ollama")
        result = self.adapter.search({"organization_id": "org-a", "knowledge_space_id": "space-a",
                                      "question": "documented revision"}, 5)
        for hit in result["hits"]:
            self.assertEqual(hit["document_id"], "org-a/space-a/doc-1")
            self.assertEqual(hit["revision"], "rev-7")
            self.assertTrue(hit["text"])


if __name__ == "__main__":
    unittest.main()
