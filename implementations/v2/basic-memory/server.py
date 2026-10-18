"""Narrow MCP façade over Basic Memory's real Markdown sync and FTS services."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from fastmcp import FastMCP
from backend import create_adapter


def build_server(corpus: Path, organization_id: str, knowledge_space_id: str) -> FastMCP:
    # Principal and scope are fixed by the trusted launcher. Tool arguments cannot
    # select a different project or organization.
    backend = create_adapter(corpus, organization_id, knowledge_space_id)
    server = FastMCP("basic-memory-scoped")

    @server.tool(name="search_memory", description="Search the authenticated Basic Memory scope")
    async def search_memory(question: str, top_k: int = 5) -> dict:
        # Basic Memory 0.13.1 exposes synchronous wrappers around asyncio.run();
        # keep its database work in a worker thread, outside FastMCP's event loop.
        return await asyncio.to_thread(backend.search, {"question": question}, top_k)

    return server


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--organization", required=True)
    parser.add_argument("--space", required=True)
    args = parser.parse_args()
    build_server(Path(args.corpus), args.organization, args.space).run(transport="stdio", show_banner=False)


if __name__ == "__main__":
    main()
