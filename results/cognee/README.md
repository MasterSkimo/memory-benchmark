# Cognee candidate

## Pilot

The frozen 20-question pilot attempted 20 queries and had 0 successful retrievals. It is **invalid for comparative retrieval** because shared corpus notes had been modified before the run; see [pilot-validity.json](pilot-validity.json). The adapter did not modify the corpus. The run read 27,456 bytes in scope; the coordinator reports the pristine corpus total as 25,556 bytes. No retrieval quality, latency, or isolation conclusion should be drawn from the run.

The real Cognee integration test observed `add` fail while retrieving its static `tiktoken` asset: the configured proxy returned **HTTP 403 Forbidden** from `openaipublic.blob.core.windows.net`. The call stopped before Cognee returned `dataset_id`, so graph/vector ingestion and retrieval did not occur. No external inference was attempted. The compact test stdout is in [integration-test.log](integration-test.log); the blocker evidence is in [blocker.md](blocker.md).

## Reproduction

See [the implementation README](../../implementations/cognee/README.md) for the Apache-2.0 SDK source, pinned setup, tests, API path, and local inference guard. The tests report 6 run, 5 passed, and 1 real vector retrieval test skipped on the documented blocker. Backend/model counts remain null when unknown.
