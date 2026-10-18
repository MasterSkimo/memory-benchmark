# Basic Memory MCP V2 candidate

This candidate serves a narrow FastMCP tool backed by Basic Memory 0.13.1's real Markdown sync, project-scoped repositories, and SQLite FTS5 search. `create_adapter(corpus, organization_id, knowledge_space_id)` fixes the trusted scope in the server process. The MCP tool accepts only the question and `top_k`; it cannot choose an organization or project. The client uses the official MCP Python SDK stdio transport and performs `initialize`, `list_tools`, and `call_tool` for each search.

Before Basic Memory opens the backend, the server validates the canonical corpus scope, rejects symlinked Markdown, and checks every document's canonical `document_id`, organization, knowledge space, and revision. Basic Memory indexes a private copy with a scope-unique permalink prefix. The client validates each returned citation against the current original source path and exact revision. The database lives under this candidate's `v2env/home/` tree and private project copies live under `runtime-home/projects/`; `runner.py` uses bubblewrap to mount Basic Memory's hardcoded `~/.basic-memory` location onto that private state while leaving HOME unchanged.

## Dependencies and verification

The exact pins are in `requirements.txt`; the complete resolved environment is in `requirements.lock`. The MCP SDK must be 1.26.0 for FastMCP 2.14.4 (`mcp==2.3.0` is incompatible). FastMCP's Docket startup also requires fakeredis 2.32.1 here; 2.40.0 no longer exports the `FakeServer` symbol Docket 0.16.6 imports.

Create the candidate environment and run the actual protocol/integration test:

```bash
python3 -m venv implementations/v2/basic-memory/v2env
implementations/v2/basic-memory/v2env/bin/pip install -r implementations/v2/basic-memory/requirements.lock
PYTHONPATH=implementations/v2/basic-memory implementations/v2/basic-memory/v2env/bin/python -m unittest discover -s implementations/v2/basic-memory -p 'test_mcp_integration.py' -v
```

The integration test covers MCP stdio initialization/tool discovery/tool invocation, two separate scopes sharing the candidate backend, cross-scope isolation, forged scope rejection, exact revision updates, forged document IDs, and symlinks. Bubblewrap namespace execution is required in this environment.
