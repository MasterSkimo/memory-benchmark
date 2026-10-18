"""Reporting must fail closed on changed inputs or evidence of a completion."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from benchkit.cloud_fixtures import create
from benchkit.cloud_report import freeze, report


class CloudEvidenceTest(unittest.TestCase):
    def test_frozen_prompt_change_rejected(self):
        """A changed prompt cannot silently reuse the same frozen run."""
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            create(root / 'fixtures')
            for name in ('AGENTS.md', 'BENCH-0001.md', 'WORKER-CONTRACT.md',
                         'PROMPT-CODEX-CLOUD.md', 'pyproject.toml',
                         'benchkit/cloud_fixtures.py', 'benchkit/trusted_evaluator.py',
                         'scripts/cloud-setup.sh'):
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source / name, target)
            shutil.copytree(source / 'config', root / 'config')
            before = freeze(root)
            self.assertEqual(before, freeze(root))
            with (root / 'config/codex/answer-prompt.txt').open('a') as changed:
                changed.write('different policy')
            with self.assertRaisesRegex(ValueError, 'Frozen inputs changed'):
                freeze(root)

    def test_completed_turn_cannot_be_reported_as_blocked(self):
        """A completion requires review, even when earlier retries had 403s."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = root / 'results/preflight'
            evidence.mkdir(parents=True)
            (evidence / 'isolation.json').write_text('{}')
            (evidence / 'luna-capability.stderr').write_text('HTTP CONNECT failed with status 403')
            (evidence / 'luna-capability.jsonl').write_text(json.dumps({'type': 'turn.completed'}) + '\n')
            with self.assertRaisesRegex(ValueError, 'completed capability turn'):
                report(root)


if __name__ == '__main__':
    unittest.main()
