# qdrant-native: BLOCKED

No implementation worker, ingestion, retrieval, answer, tenant-safety test or update test ran. Candidate dependencies and licenses were not verified or frozen. Docker and package-network access were available, but candidate services were not provisioned after the shared preflight gates failed.

Native workers share filesystem read access (non-gold canary read succeeded); the native spawn schema has no filesystem or tool-scope selector. The controlled CLI namespace denied tested evaluator paths and supported built-in ChatGPT login, but its Luna model probe received HTTP CONNECT 403 and timed out after 45 seconds. No completion, served model ID or token usage was supplied. Implicit ChatGPT MCP connection attempts also occurred despite a clean home and ignored user config; a working runner must explicitly constrain tool availability.

JSONL records are NOT_RUN placeholders for the frozen 20 questions under cold/warm conditions. Null telemetry is not zero use. They must not be passed to a scorer as successful abstentions. See ../preflight/ for raw capability evidence.
