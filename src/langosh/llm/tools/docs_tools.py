"""Docs tools — read-only access to the LangChain/LangGraph/LangSmith docs MCP server."""

from __future__ import annotations

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

_DOCS_URL = "https://docs.langchain.com/mcp"

# Remote tool names (as exposed by the MCP server)
_REMOTE_SEARCH = "search_docs_by_lang_chain"
_REMOTE_FS = "query_docs_filesystem_docs_by_lang_chain"


_DOCS_SEARCH = {
    "name": "docs_search",
    "description": (
        "Search the official LangChain/LangGraph/LangSmith documentation. "
        "Returns relevant doc snippets with page paths. Use this FIRST to find "
        "the right page, then use docs_read to fetch full content. "
        "Query like: 'StateGraph conditional edges', 'create_react_agent tools', "
        "'checkpointing memory'."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query — use natural language or keywords.",
            },
        },
        "required": ["query"],
    },
}

_DOCS_READ = {
    "name": "docs_read",
    "description": (
        "Run a filesystem-style command against the docs virtual filesystem. "
        "Supports: cat/head/ls/tree/find/grep/rg. Use this to read full page "
        "content (e.g., 'cat langgraph/concepts/stategraph.mdx') or explore "
        "structure (e.g., 'tree langgraph' or 'rg \"interrupt\" langgraph')."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Shell-like command (cat/head/ls/tree/find/grep/rg) on the docs filesystem.",
            },
        },
        "required": ["command"],
    },
}


async def _call_remote(tool_name: str, args: dict) -> str:
    """Open an MCP session, call one tool, return its text content."""
    async with streamablehttp_client(_DOCS_URL) as (read, write, _get_session_id):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments=args)
            parts = []
            for block in result.content or []:
                text = getattr(block, "text", None)
                if text:
                    parts.append(text)
                else:
                    parts.append(str(block))
            return "\n".join(parts) if parts else "(no content)"


async def docs_search(args: dict) -> str:
    query = args.get("query", "").strip()
    if not query:
        return "Error: 'query' is required."
    try:
        return await _call_remote(_REMOTE_SEARCH, {"query": query})
    except Exception as e:
        return f"Error calling docs_search: {e}"


async def docs_read(args: dict) -> str:
    command = args.get("command", "").strip()
    if not command:
        return "Error: 'command' is required."
    try:
        return await _call_remote(_REMOTE_FS, {"command": command})
    except Exception as e:
        return f"Error calling docs_read: {e}"


TOOLS = [_DOCS_SEARCH, _DOCS_READ]

DISPATCH = {
    "docs_search": docs_search,
    "docs_read": docs_read,
}
