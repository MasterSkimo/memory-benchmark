#!/usr/bin/env bash
# Only the frozen 40-question V2 R pilot; native E dispatch is documented separately.
set -euo pipefail
cd "$(dirname "$0")/.."
args=(--corpus fixtures/v2/vault --questions fixtures/v2/questions.jsonl --frozen-manifest results/v2/frozen-evaluation.json)
python3 -m benchkit.v2.harness --candidate luna-vault-direct --adapter implementations/v2/luna-vault-direct/scoped_vault.py --out results/v2/luna-vault-direct/retrieval "${args[@]}"
PYTHONPATH=implementations/v2/common-models implementations/v2/common-models/.venv/bin/python -m benchkit.v2.harness --candidate qdrant-native --adapter implementations/v2/qdrant-native/adapter.py --out results/v2/qdrant-native/retrieval "${args[@]}"
# Basic Memory's bubblewrap launcher requires namespace support; MCP uses local IPC.
implementations/v2/basic-memory/v2env/bin/python -m benchkit.v2.harness --candidate basic-memory --adapter implementations/v2/basic-memory/adapter.py --out results/v2/basic-memory/retrieval "${args[@]}"
