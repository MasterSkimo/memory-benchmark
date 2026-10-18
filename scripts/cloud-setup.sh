#!/usr/bin/env bash
# Deterministic Codex Cloud bootstrap. Installs no external dependencies.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 --version
python3 -m benchkit.cloud_fixtures --out fixtures
python3 -m unittest discover -s tests -v
python3 -m benchkit.smoke
# The private gold answers are generated ONLY in a separate evaluator environment.
