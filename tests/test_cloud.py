"""Smoke coverage for Codex Cloud fixture preparation."""
import json
import tempfile
import unittest
from pathlib import Path
from benchkit.cloud_fixtures import create
class CloudFixturesTest(unittest.TestCase):
    """Check repeatable corpus and absence of benchmark gold."""
    def test_generated_dataset(self):
        """Generate and check public data counts."""
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/"public"
            manifest=create(root)
            self.assertEqual(manifest["notes"],1000)
            self.assertEqual(manifest["questions"],200)
            self.assertFalse((root/"private").exists())
            rows=[json.loads(line) for line in (root/"questions_public_pilot.jsonl").read_text().splitlines()]
            self.assertEqual(len(rows),20)
    def test_reproducibility(self):
        """Same seed must produce identical content digests."""
        with tempfile.TemporaryDirectory() as folder:
            a=create(Path(folder)/"one")
            b=create(Path(folder)/"two")
            self.assertEqual(a["vault_sha256"],b["vault_sha256"])
if __name__=="__main__":unittest.main()
