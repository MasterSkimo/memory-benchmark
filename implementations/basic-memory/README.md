# Basic Memory candidate

This adapter uses Basic Memory 0.13.1's Markdown parser/sync service, project-scoped entity and search repositories, and SQLite FTS5 search service. It validates the source scope and every Markdown document, copies only that scope into candidate-local storage, then lets Basic Memory sync the copy. Results are checked against the original source frontmatter and canonical source path. To handle natural language questions, it converts content words into quoted FTS5 terms joined with `OR`; FTS5 supplies the search and ranking.

The adapter fixes authorization in `create_adapter(corpus, organization_id, knowledge_space_id)`. It maps the hashed scope tuple to one Basic Memory project, constructs repositories with that project's ID, rejects mismatched scope fields on each question, and validates each returned source path and required frontmatter. Basic Memory 0.13.1 hardcodes `HOME/.basic-memory` without a supported config-root option. `run.py` keeps the HOME string unchanged and uses bubblewrap to mount candidate-local Basic Memory state at that path. Basic Memory's Python services are used directly; its CLI/MCP entry point is not used because package dependency resolution currently selects an incompatible FastMCP release.

## Reproduction

Python 3.12 is used in the pilot. Create the candidate-local environment and run the real integration test:

```bash
python3 -m venv implementations/basic-memory/.venv
implementations/basic-memory/.venv/bin/pip install -r implementations/basic-memory/requirements.lock
python3 implementations/basic-memory/run.py implementations/basic-memory/.venv/bin/python -m unittest discover -s implementations/basic-memory -p test_adapter.py -v
```

Run tests and retrieval through `run.py`, which keeps HOME unchanged while bubblewrap mounts candidate-local `.basic-memory` persistence at Basic Memory's normal config path. The managed execution environment must allow bubblewrap namespaces and local asyncio socketpair/thread callbacks for `aiosqlite`. Run the frozen retrieval pilot with:

```bash
python3 implementations/basic-memory/run.py implementations/basic-memory/.venv/bin/python -m benchkit.pilot \
  --candidate basic-memory \
  --adapter implementations/basic-memory/adapter.py \
  --out results/basic-memory
```

The Basic Memory package is pinned to 0.13.1 (AGPL-3.0-or-later; source: https://github.com/basicmachines-co/basic-memory). Runtime model/provider usage is not applicable. `backend_calls` is one Basic Memory FTS search invocation per question. `file_reads` and `bytes_read` count the adapter's reads of returned original source files for provenance; internal SQLite/FTS I/O is not exposed. The runner reports ingestion counters as null because it does not expose the sync service's internal file/backend counters. Ingestion and indexing happen during adapter construction and are not included in per-question search timing.
