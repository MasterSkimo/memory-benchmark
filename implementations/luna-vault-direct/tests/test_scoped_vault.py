import tempfile
import unittest
from pathlib import Path

from native_tool import frozen_vault_digest, invoke
from scoped_vault import ScopeError, ScopedMarkdownVault


def note(org="org-a", space="project-1", revision="r1", body="alpha durable fact"):
    return (f"---\ndocument_id: {org}/{space}/one\norganization_id: {org}\n"
            f"knowledge_space_id: {space}\nrevision: {revision}\n---\n\n{body}\n")


class ScopedVaultTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for org, space, text in (("org-a", "project-1", note()),
                                 ("org-a", "project-2", note(space="project-2", body="secret project two")),
                                 ("org-b", "project-1", note(org="org-b", body="secret org two"))):
            target = self.root / org / space / "one.md"
            target.parent.mkdir(parents=True)
            target.write_text(text, encoding="utf-8")
        self.vault = ScopedMarkdownVault(self.root, "org-a", "project-1")

    def tearDown(self):
        self.temp.cleanup()

    def test_list_read_and_search_include_provenance_and_counts(self):
        self.assertEqual(self.vault.list_markdown(), ["one.md"])
        result = self.vault.search("alpha durable", top_k=2)
        self.assertEqual(result["hits"][0]["document_id"], "org-a/project-1/one")
        self.assertEqual(result["hits"][0]["revision"], "r1")
        read = self.vault.read_markdown("one.md")
        self.assertIn("alpha durable fact", read["text"])
        self.assertEqual(read["revision"], "r1")
        self.assertEqual(self.vault.read_markdown("org-a/project-1/one")["document_id"],
                         "org-a/project-1/one")
        self.assertEqual(result["backend_calls"], None)
        self.assertGreater(result["bytes_read"], 0)

    def test_mismatched_request_identity_is_rejected_before_io(self):
        before = self.vault.counters.read_calls
        with self.assertRaises(ScopeError):
            self.vault.search("secret", organization_id="org-b")
        with self.assertRaises(ScopeError):
            self.vault.list_markdown(knowledge_space_id="project-2")
        self.assertEqual(self.vault.counters.read_calls, before)

    def test_traversal_and_alternate_scope_identifiers_are_rejected(self):
        for name in ("../project-2/one.md", "/etc/passwd", "..\\org-b\\one.md",
                     "org-b/project-1/one", "org-b/project-1/one.md"):
            with self.subTest(name=name), self.assertRaises((ScopeError, FileNotFoundError)):
                self.vault.read_markdown(name)

    def test_symlink_source_and_directory_are_never_listed_or_read(self):
        outside = self.root / "org-a" / "project-2" / "one.md"
        scoped = self.root / "org-a" / "project-1"
        (scoped / "leak.md").symlink_to(outside)
        self.assertEqual(self.vault.list_markdown(), ["one.md"])
        with self.assertRaises(ScopeError):
            self.vault.read_markdown("leak.md")
        (scoped / "linked").symlink_to(outside.parent, target_is_directory=True)
        self.assertEqual(self.vault.list_markdown(), ["one.md"])
        with self.assertRaises(ScopeError):
            self.vault.read_markdown("linked/one.md")

    def test_frontmatter_cannot_spoof_a_foreign_document_id(self):
        path = self.root / "org-a" / "project-1" / "one.md"
        path.write_text(note().replace("document_id: org-a/project-1/one",
                                       "document_id: org-b/project-1/one"), encoding="utf-8")
        with self.assertRaises(ScopeError):
            self.vault.read_markdown("one.md")

    def test_native_tool_audits_calls_and_enforces_question_call_limit(self):
        event_root = self.root / "events"
        result = invoke({"op": "read", "document_id": "org-a/project-1/one"},
                        corpus_root=self.root, organization_id="org-a",
                        knowledge_space_id="project-1", question_id="q-test",
                        events_root=event_root,
                        expected_vault_sha256=frozen_vault_digest(self.root)[0])
        self.assertEqual(result["revision"], "r1")
        import json
        rows = [json.loads(line) for line in (event_root / "q-test.jsonl").read_text().splitlines()]
        self.assertEqual(rows[0]["file_reads"], 1)
        self.assertEqual(rows[0]["source_ids"], ["org-a/project-1/one"])
        for _ in range(11):
            invoke({"op": "list"}, corpus_root=self.root, organization_id="org-a",
                   knowledge_space_id="project-1", question_id="q-test", events_root=event_root,
                   expected_vault_sha256=frozen_vault_digest(self.root)[0])
        with self.assertRaises(RuntimeError):
            invoke({"op": "list"}, corpus_root=self.root, organization_id="org-a",
                   knowledge_space_id="project-1", question_id="q-test", events_root=event_root,
                   expected_vault_sha256=frozen_vault_digest(self.root)[0])

    def test_integrity_guard_refuses_digest_mismatch(self):
        event_root = self.root / "events"
        result = invoke({"op": "list"}, corpus_root=self.root, organization_id="org-a",
                        knowledge_space_id="project-1", question_id="q-mismatch",
                        events_root=event_root, expected_vault_sha256="0" * 64)
        self.assertEqual(result["audit"]["status"], "CORPUS_INTEGRITY_FAILURE")
        self.assertEqual(result["audit"]["file_reads"], 0)
        self.assertFalse(result["audit"]["pristine_verified"])


if __name__ == "__main__":
    unittest.main()
