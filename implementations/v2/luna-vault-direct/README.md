# V2 direct Markdown control

This candidate performs no indexing, embeddings, or answer generation. The retriever factory is `create_adapter(corpus, organization_id, knowledge_space_id)` and returns an object with `.search(question_record, top_k=5)` for the neutral V2 retrieval harness. It scans only the fixed organization/project Markdown scope.

For native answer sessions, `native_tool.py` invokes the shared `benchkit/v2/answer_tool.py` `BoundAnswerTool`. The coordinator supplies a session config binding question ID, trusted principal scope, corpus root, opaque session handle, and SHA-256 of a session token. The model request contains only handle + operation data; scope, paths, and tenant filters are rejected. Set `BENCH_SESSION_TOKEN` through the trusted launcher, never from model arguments. The interface supports list/read/search with a maximum top-k of five and a persistent per-question call budget. Wrapper events and backend calls are separate. Native runtime tokens remain null unless actually exported.

Give each run a unique audit path in the trusted config, such as `results/v2/luna-vault-direct/events/<run-id>/<question-id>.jsonl`; fresh sessions must not reuse a previous session's event file. The CLI accepts one JSON operation per process, and reloads the event count so its 12-call limit persists across tool invocations. The native runtime must still be treated as exploratory if it cannot hide other tools.

The native Luna runtime may still expose tools outside this wrapper. Therefore end-to-end comparisons remain exploratory unless the runtime enforces tool capability restrictions. The internal API independently rejects forged scope and path fields.
