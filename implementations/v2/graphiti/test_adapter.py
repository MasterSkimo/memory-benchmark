"""Graphiti integration tests; model-backed tests require local services and V2 data."""
import os
import unittest
from pathlib import Path

from adapter import _local_url, create_adapter
from adapter import _shared_local_embedder


class SharedNeuralEmbeddingTest(unittest.TestCase):
    def test_checkpoint_integrity_dimensions_and_normalization(self):
        model = _shared_local_embedder()
        vectors = model.encode(["decision finale du projet", "final project decision"])
        self.assertEqual(model.model_revision,
                         "db50044db53237fb6f280a7b0c27eb0be45ff18f7108bcd61ea24640cbb15daf")
        self.assertEqual(model.dimension, 384)
        self.assertEqual(model.normalization, "l2")
        self.assertEqual(len(vectors), 2)
        for vector in vectors:
            self.assertEqual(len(vector), 384)
            self.assertAlmostEqual(sum(value * value for value in vector) ** 0.5, 1.0, places=5)


class LocalModelBoundaryTest(unittest.TestCase):
    def test_rejects_remote_llm_endpoint(self):
        name = "GRAPHITI_LOCAL_LLM_BASE_URL"
        previous = os.environ.get(name)
        os.environ[name] = "https://provider.example/v1"
        try:
            with self.assertRaisesRegex(ValueError, "loopback"):
                _local_url(name, "http://127.0.0.1/v1")
        finally:
            if previous is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = previous


class GraphitiLocalModelIntegrationTest(unittest.TestCase):
    """Checks real extraction and temporal graph retrieval when assets are ready."""
    @classmethod
    def setUpClass(cls):
        cls.corpus = Path(__file__).parents[3] / "fixtures" / "v2" / "vault"
        if not cls.corpus.exists():
            raise unittest.SkipTest("V2 fixtures/v2/vault has not been provisioned")
        if not os.getenv("GRAPHITI_LOCAL_LLM_MODEL"):
            raise unittest.SkipTest("pinned local LLM for Graphiti extraction is unavailable")

    def test_native_graph_extraction_and_temporal_retrieval(self):
        adapter = create_adapter(self.corpus, "org-alto", "project-01")
        try:
            result = adapter.search({"question": "What is Iris's current records retention decision?",
                                     "organization_id": "org-alto",
                                     "knowledge_space_id": "project-01"})
            self.assertGreater(result["graph_facts"], 0)
            self.assertGreater(adapter.local_llm.request_count, 0)
            self.assertGreater(adapter.local_embedder.request_count, 0)
            self.assertGreater(adapter.episodes_ingested, 0)
            self.assertIn("org-alto/project-01/note-050",
                          [h["document_id"] for h in result["hits"]])
            old = adapter.search({"question": "Before May 1 2026, what was Iris's records retention?",
                                  "as_of": "2026-04-30T23:59:59+00:00",
                                  "organization_id": "org-alto",
                                  "knowledge_space_id": "project-01"})
            self.assertIn("org-alto/project-01/note-040",
                          [h["document_id"] for h in old["hits"]])
            deployment = adapter.search({"question": "What is the current Iris deployment approval rule?",
                                         "organization_id": "org-alto",
                                         "knowledge_space_id": "project-01"})
            self.assertIn(("org-alto/project-01/note-060", "v2-r2"),
                          [(h["document_id"], h["revision"]) for h in deployment["hits"]])
            self.assertTrue(all(h["document_id"].startswith("org-alto/project-01/")
                                for h in result["hits"] + old["hits"] + deployment["hits"]))
            with self.assertRaises(PermissionError):
                adapter.search({"question": "secret", "organization_id": "forged",
                                "knowledge_space_id": "project-01"})
        finally:
            adapter.close()


if __name__ == "__main__":
    unittest.main()
