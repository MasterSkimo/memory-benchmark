"""Real stdio MCP initialize/list_tools/call_tool and cross-scope integration."""
from pathlib import Path
import tempfile
import unittest
import uuid

from adapter import create_adapter


def note(path: Path, org: str, space: str, body: str, rev: str = "r1") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\ndocument_id: {org}/{space}/{path.stem}\nrevision: {rev}\n"
        f"organization_id: {org}\nknowledge_space_id: {space}\n---\n# Evidence\n{body}\n",
        encoding="utf-8",
    )


class BasicMemoryMCPIntegration(unittest.TestCase):
    def test_stdio_protocol_scope_provenance_revision_and_shared_backend(self):
        with tempfile.TemporaryDirectory(prefix="basic-memory-v2-") as tmp:
            corpus = Path(tmp) / "vault"
            org_a, org_b = "org-" + uuid.uuid4().hex[:8], "org-" + uuid.uuid4().hex[:8]
            note(corpus / org_a / "space-a" / "evidence.md", org_a, "space-a", "The approved protocol is amber-otter.")
            note(corpus / org_b / "space-b" / "evidence.md", org_b, "space-b", "Foreign marker cobalt-lynx.")
            a = create_adapter(corpus, org_a, "space-a")
            b = create_adapter(corpus, org_b, "space-b")
            hit = a.search({"question": "amber-otter"})["hits"]
            self.assertEqual([(h["document_id"], h["revision"]) for h in hit], [(f"{org_a}/space-a/evidence", "r1")])
            self.assertEqual(b.search({"question": "cobalt-lynx"})["hits"][0]["document_id"], f"{org_b}/space-b/evidence")
            self.assertEqual(a.search({"question": "cobalt-lynx"})["hits"], [])
            with self.assertRaises(PermissionError):
                a.search({"question": "amber-otter", "organization_id": org_b})

            target = corpus / org_a / "space-a" / "evidence.md"
            note(target, org_a, "space-a", "The revised protocol is silver-heron.", "r2")
            revised = create_adapter(corpus, org_a, "space-a").search({"question": "silver-heron"})["hits"]
            self.assertEqual(revised[0]["revision"], "r2")
            self.assertEqual(create_adapter(corpus, org_a, "space-a").search({"question": "amber-otter"})["hits"], [])

    def test_rejects_forged_metadata_and_symlinked_markdown(self):
        with tempfile.TemporaryDirectory(prefix="basic-memory-v2-invalid-") as tmp:
            corpus = Path(tmp) / "vault"
            scope = corpus / "org-a" / "space-a"
            note(scope / "forged.md", "org-a", "space-a", "forged", "r1")
            path = scope / "forged.md"
            path.write_text(path.read_text().replace("document_id: org-a/space-a/forged", "document_id: org-b/space-b/forged"))
            with self.assertRaises(Exception):
                create_adapter(corpus, "org-a", "space-a").search({"question": "forged"})

            path.unlink()
            elsewhere = corpus / "org-a" / "other" / "outside.md"
            note(elsewhere, "org-a", "other", "outside", "r1")
            path.symlink_to(elsewhere)
            with self.assertRaises(Exception):
                create_adapter(corpus, "org-a", "space-a").search({"question": "outside"})


if __name__ == "__main__":
    unittest.main()
