"""Public adapter that talks to a real Basic Memory MCP server over stdio."""
from __future__ import annotations
import asyncio
import json
import os
from pathlib import Path
import sys
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


class BasicMemoryMCPAdapter:
    def __init__(self, corpus, organization_id: str, knowledge_space_id: str):
        self.corpus = Path(corpus).resolve(strict=True)
        self.organization_id = organization_id
        self.knowledge_space_id = knowledge_space_id
        for part in (organization_id, knowledge_space_id):
            if not isinstance(part, str) or not part or part in {".", ".."} or "/" in part or "\\" in part:
                raise ValueError("organization and knowledge-space IDs must be safe path components")
        self.server_script = Path(__file__).resolve().parent / "runner.py"
        self.python = Path(__file__).resolve().parent / "v2env" / "bin" / "python"
        if not self.python.exists():
            raise RuntimeError("V2 environment missing; install requirements.lock into implementations/v2/basic-memory/v2env")

    async def _call(self, question: str, top_k: int):
        params = StdioServerParameters(
            command=str(self.python),
            args=[str(self.server_script), "--corpus", str(self.corpus),
                  "--organization", self.organization_id, "--space", self.knowledge_space_id],
            env={**os.environ, "PYTHONPATH": str(self.server_script.parent)},
            cwd=str(self.server_script.parent),
        )
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools = await session.list_tools()
                if not any(t.name == "search_memory" for t in tools.tools):
                    raise RuntimeError("Basic Memory MCP did not expose search_memory")
                result = await session.call_tool("search_memory", {"question": question, "top_k": top_k})
                if result.isError:
                    raise RuntimeError("Basic Memory MCP search failed: " + str(result.content))
                # FastMCP encodes Python dictionaries as JSON text content.
                for item in result.content:
                    if getattr(item, "type", None) == "text":
                        try:
                            return json.loads(item.text)
                        except json.JSONDecodeError:
                            continue
                structured = getattr(result, "structuredContent", None)
                if isinstance(structured, dict):
                    return structured
                raise RuntimeError("Basic Memory MCP returned no structured search result")

    def search(self, question: dict, top_k: int = 5) -> dict:
        if not isinstance(question, dict):
            raise ValueError("question must be an object")
        if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 1:
            raise ValueError("top_k must be a positive integer")
        for key, expected in (("organization_id", self.organization_id), ("knowledge_space_id", self.knowledge_space_id)):
            if key in question and question[key] != expected:
                raise PermissionError(f"question {key} differs from adapter authorization")
        query = question.get("question") or question.get("text") or question.get("query") or ""
        if not isinstance(query, str) or not query.strip():
            raise ValueError("question must contain non-empty question/text/query")
        result = asyncio.run(self._call(query, top_k))
        if not isinstance(result, dict) or not isinstance(result.get("hits"), list):
            raise RuntimeError("Basic Memory MCP returned an invalid result")
        # Reopen the original scoped source and bind every returned citation to its
        # current exact frontmatter identity and revision.
        import frontmatter
        scope = self.corpus / self.organization_id / self.knowledge_space_id
        for hit in result["hits"]:
            doc_id, revision = hit.get("document_id"), hit.get("revision")
            prefix = self.organization_id + "/" + self.knowledge_space_id + "/"
            if not isinstance(doc_id, str) or not doc_id.startswith(prefix):
                raise PermissionError("MCP returned a document outside the authorized scope")
            if not isinstance(revision, (str, int)) or not str(revision).strip():
                raise RuntimeError("MCP returned a document without an exact revision")
            relative = Path(doc_id + ".md")
            source = (self.corpus / relative)
            if source.is_symlink() or not source.is_file() or scope.resolve() not in source.resolve().parents:
                raise PermissionError("MCP returned an unsafe or missing source path")
            metadata = frontmatter.load(source).metadata
            canonical_id = source.relative_to(self.corpus).with_suffix("").as_posix()
            if metadata.get("document_id") != canonical_id or doc_id != canonical_id:
                raise PermissionError("MCP returned forged document metadata")
            if metadata.get("organization_id") != self.organization_id or metadata.get("knowledge_space_id") != self.knowledge_space_id:
                raise PermissionError("MCP returned forged scope metadata")
            if str(metadata.get("revision")) != str(revision):
                raise RuntimeError("MCP returned a stale document revision")
        return result


def create_adapter(corpus, organization_id, knowledge_space_id):
    return BasicMemoryMCPAdapter(corpus, organization_id, knowledge_space_id)
