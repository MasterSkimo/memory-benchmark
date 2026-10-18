# Cognee blocker and run qualification

The real integration test observed Cognee `add` fail while retrieving its static tiktoken encoding asset: `openaipublic.blob.core.windows.net` returned **HTTP 403 Forbidden** through the configured proxy. The attempt stopped before Cognee returned `dataset_id`, so no graph/vector ingestion or retrieval occurred. No external inference was attempted. The saved test output is `integration-test.log`; it contains test status and the compact error only.

The one frozen 20-question pilot attempted 20 queries and had 0 successful retrievals. It is not valid comparative R evidence: shared corpus notes had been modified by another worker before this run. The measured scope read total was 27,456 bytes; the coordinator reports pristine notes total 25,556 bytes. No quality, latency, or isolation conclusion should be drawn from those attempts. The adapter did not modify corpus files.

The failed pilot used adapter SHA-256 `49225170e4d1625d9b6a6631e3aed23261fa59c58a243f8ea27f47d98cd99bcb` (also retained in `retrieval-summary.json`). Live code was hardened afterward; its current hash is recorded in `manifest.json`. These are separate artifacts. The pilot was not rerun after hardening.

Test command:

```sh
implementations/cognee/.venv/bin/python -m unittest discover -s implementations/cognee -p 'test_*.py' -v
```

Current integration test result: 6 tests run, 5 passed, 1 real vector retrieval test skipped at the documented `add` blocker.
