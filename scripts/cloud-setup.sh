#!/usr/bin/env bash
# Deterministic bootstrap for Codex Cloud: no external package installs or model calls.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 --version
python3 -m benchkit.cloud_fixtures --out fixtures/public
# Private answers must live OUTSIDE the repository tree and agent workspace.
echo 'NOTE: evaluator-only oracle must be generated in a separate isolated environment.'
python3 -m unittest discover -s tests -v
