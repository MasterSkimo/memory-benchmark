"""Real Cognee add-stage integration and authorization boundary checks."""
from __future__ import annotations

import tempfile
import sqlite3
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit
from unittest.mock import patch

from adapter import (
    _explicit_local_llm_configured,
    _is_loopback_endpoint,
    create_adapter,
)


def _write_note(root: Path, revision: str = "r1", document_id: str = "doc-1") -> Path:
    scoped = root / "org-a" / "space-a"
    scoped.mkdir(parents=True, exist_ok=True)
    note = scoped / f"{document_id}.md"
    note.write_text(
        f"---\ndocument_id: org-a/space-a/{document_id}\n"
        "organization_id: org-a\nknowledge_space_id: space-a\n"
        f"revision: {revision}\n---\n# Operations\n"
        "The local processing record retains its exact source revision.\n",
        encoding="utf-8",
    )
    return note


class RealCogneeAddTests(unittest.TestCase):
    def test_real_add_returns_dataset_and_uses_shared_local_embedding(self):
        with tempfile.TemporaryDirectory(prefix="cognee-v2-add-") as temp:
            root = Path(temp)
            _write_note(root)
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                adapter = create_adapter(root, "org-a", "space-a")

            self.assertEqual(adapter.ingestion_status, "COMPLETED")
            self.assertIsNotNone(adapter.dataset_id)
            self.assertTrue(adapter.dataset_name.startswith("bench_"))
            self.assertEqual(adapter.add_llm_preflight, "SKIPPED_ADD_ONLY_NO_LOCAL_LLM")
            self.assertGreaterEqual(adapter.embedding_calls, 1)
            self.assertEqual(adapter.extraction_status, "BLOCKED_NO_LOCAL_LLM")
            self.assertEqual(
                set(adapter._sources),
                {"org-a/space-a/doc-1"},
            )
            self.assertEqual(adapter._sources["org-a/space-a/doc-1"]["revision"], "r1")

            # Verify Cognee's native relational dataset is the requested
            # revision-scoped namespace and that its linked data keeps source
            # provenance in the persisted raw text.
            database = Path(__file__).resolve().parent / ".state/system/databases/cognee_db"
            connection = sqlite3.connect(database)
            try:
                native_id = str(adapter.dataset_id).replace("-", "")
                rows = connection.execute(
                    "SELECT datasets.name, data.raw_data_location "
                    "FROM datasets JOIN dataset_data ON dataset_data.dataset_id = datasets.id "
                    "JOIN data ON data.id = dataset_data.data_id WHERE datasets.id = ?",
                    (native_id,),
                ).fetchall()
            finally:
                connection.close()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][0], adapter.dataset_name)
            stored_text = Path(urlsplit(rows[0][1]).path).read_text(encoding="utf-8")
            self.assertIn("document_id: org-a/space-a/doc-1", stored_text)
            self.assertIn("revision: r1", stored_text)

            # Search must stop before Cognee access because cognify was not run.
            with self.assertRaisesRegex(RuntimeError, "BLOCKED_EXTRACTION"):
                adapter.search(
                    {
                        "organization_id": "org-a",
                        "knowledge_space_id": "space-a",
                        "question": "Which revision is current?",
                    },
                    5,
                )

    def test_revision_change_creates_a_fresh_backend_dataset(self):
        with tempfile.TemporaryDirectory(prefix="cognee-v2-revision-") as temp:
            root = Path(temp)
            note = _write_note(root, revision="r1")
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                first = create_adapter(root, "org-a", "space-a")
            note.write_text(note.read_text(encoding="utf-8").replace("revision: r1", "revision: r2"),
                            encoding="utf-8")
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                second = create_adapter(root, "org-a", "space-a")

            self.assertNotEqual(first.dataset_name, second.dataset_name)
            self.assertNotEqual(first.dataset_id, second.dataset_id)
            self.assertEqual(second._sources["org-a/space-a/doc-1"]["revision"], "r2")


class AuthorizationTests(unittest.TestCase):
    def test_foreign_scope_metadata_and_forged_document_path_fail_before_add(self):
        with tempfile.TemporaryDirectory(prefix="cognee-v2-forged-") as temp:
            root = Path(temp)
            note = _write_note(root)
            note.write_text(
                note.read_text(encoding="utf-8").replace(
                    "document_id: org-a/space-a/doc-1",
                    "document_id: org-b/space-z/secret",
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "outside its authorized"):
                create_adapter(root, "org-a", "space-a")

    def test_filename_and_frontmatter_document_id_must_match_exactly(self):
        with tempfile.TemporaryDirectory(prefix="cognee-v2-forged-id-") as temp:
            root = Path(temp)
            note = _write_note(root)
            note.write_text(
                note.read_text(encoding="utf-8").replace(
                    "document_id: org-a/space-a/doc-1",
                    "document_id: org-a/space-a/another-note",
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "does not match its authorized source path"):
                create_adapter(root, "org-a", "space-a")

    def test_path_components_and_symlink_sources_are_rejected(self):
        with tempfile.TemporaryDirectory(prefix="cognee-v2-path-") as temp:
            root = Path(temp)
            with self.assertRaisesRegex(ValueError, "path component"):
                create_adapter(root, "../org-a", "space-a")
            scoped = root / "org-a" / "space-a"
            scoped.mkdir(parents=True)
            outside = root / "outside.md"
            outside.write_text("private", encoding="utf-8")
            (scoped / "link.md").symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "escapes its authorized directory"):
                create_adapter(root, "org-a", "space-a")

    def test_local_llm_config_requires_loopback_and_opt_in(self):
        llm = SimpleNamespace(
            llm_provider="ollama",
            llm_endpoint="http://127.0.0.1:11434",
            structured_output_framework="instructor",
            fallback_endpoint="",
            baml_llm_endpoint="",
        )
        with patch.dict("os.environ", {"COGNEE_LOCAL_INFERENCE_OPT_IN": "1"}):
            self.assertTrue(_explicit_local_llm_configured(llm))
            self.assertFalse(
                _explicit_local_llm_configured(
                    SimpleNamespace(**{**vars(llm), "llm_endpoint": "https://llm.example/api"})
                )
            )
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(_explicit_local_llm_configured(llm))
        self.assertFalse(_is_loopback_endpoint("https://user:pass@127.0.0.1:11434"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
