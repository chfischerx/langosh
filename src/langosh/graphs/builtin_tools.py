"""Curated registry of LangChain community tools usable directly from mcp.json.

Each entry carries everything we need to (a) render it in the builder catalog
and (b) emit import + ctor code in the generated graph module.

Adding a tool here is the entire integration — no manifest step, no runtime
discovery on the server. The compiled graph imports each tool directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BuiltinTool:
    """A curated LangChain community tool."""

    key: str
    name: str
    description: str
    parameters: tuple[dict, ...]
    imports: tuple[str, ...]
    ctor: str


_WIKIPEDIA = BuiltinTool(
    key="wikipedia",
    name="wikipedia",
    description=(
        "Search Wikipedia and return the top article summary. Use for "
        "encyclopedic facts, biographies, dates, geography, etc."
    ),
    parameters=(
        {"name": "query", "type": "str", "required": True, "description": "Search query."},
    ),
    imports=(
        "from langchain_community.tools import WikipediaQueryRun",
        "from langchain_community.utilities import WikipediaAPIWrapper",
    ),
    ctor="WikipediaQueryRun(api_wrapper=WikipediaAPIWrapper())",
)


_DDG_SEARCH = BuiltinTool(
    key="ddg_search",
    name="duckduckgo_search",
    description=(
        "Search the web via DuckDuckGo and return snippets. Good general-"
        "purpose web search that doesn't require an API key."
    ),
    parameters=(
        {"name": "query", "type": "str", "required": True, "description": "Search query."},
    ),
    imports=("from langchain_community.tools import DuckDuckGoSearchRun",),
    ctor="DuckDuckGoSearchRun()",
)


_TAVILY_SEARCH = BuiltinTool(
    key="tavily_search",
    name="tavily_search",
    description=(
        "High-quality AI-optimized web search via Tavily. Returns ranked "
        "snippets with URLs. Requires TAVILY_API_KEY env var on the server."
    ),
    parameters=(
        {"name": "query", "type": "str", "required": True, "description": "Search query."},
    ),
    imports=("from langchain_community.tools.tavily_search import TavilySearchResults",),
    ctor="TavilySearchResults(max_results=5)",
)


_PYTHON_REPL = BuiltinTool(
    key="python_repl",
    name="python_repl",
    description=(
        "Execute Python code in a sandboxed REPL. Returns stdout. Useful for "
        "math, data transformation, and running small scripts."
    ),
    parameters=(
        {"name": "query", "type": "str", "required": True, "description": "Python code to execute."},
    ),
    imports=("from langchain_experimental.tools import PythonREPLTool",),
    ctor="PythonREPLTool()",
)


_ARXIV = BuiltinTool(
    key="arxiv",
    name="arxiv",
    description="Search arxiv.org for scientific papers by keyword or ID.",
    parameters=(
        {"name": "query", "type": "str", "required": True, "description": "Search query or arxiv id."},
    ),
    imports=(
        "from langchain_community.tools import ArxivQueryRun",
        "from langchain_community.utilities import ArxivAPIWrapper",
    ),
    ctor="ArxivQueryRun(api_wrapper=ArxivAPIWrapper())",
)


_PUBMED = BuiltinTool(
    key="pubmed",
    name="pubmed",
    description="Search PubMed for biomedical literature by keyword.",
    parameters=(
        {"name": "query", "type": "str", "required": True, "description": "Search query."},
    ),
    imports=(
        "from langchain_community.tools.pubmed.tool import PubmedQueryRun",
        "from langchain_community.utilities.pubmed import PubMedAPIWrapper",
    ),
    ctor="PubmedQueryRun(api_wrapper=PubMedAPIWrapper())",
)


_STACKEXCHANGE = BuiltinTool(
    key="stackexchange",
    name="stackexchange",
    description=(
        "Search Stack Exchange (Stack Overflow by default) for programming "
        "Q&A matching a query."
    ),
    parameters=(
        {"name": "query", "type": "str", "required": True, "description": "Search query."},
    ),
    imports=(
        "from langchain_community.tools.stackexchange.tool import StackExchangeTool",
        "from langchain_community.utilities.stackexchange import StackExchangeAPIWrapper",
    ),
    ctor="StackExchangeTool(api_wrapper=StackExchangeAPIWrapper())",
)


_YOUTUBE_SEARCH = BuiltinTool(
    key="youtube_search",
    name="youtube_search",
    description=(
        "Search YouTube for video URLs matching a query. Returns a list of "
        "URLs, not transcripts."
    ),
    parameters=(
        {"name": "query", "type": "str", "required": True, "description": "Search query."},
    ),
    imports=("from langchain_community.tools import YouTubeSearchTool",),
    ctor="YouTubeSearchTool()",
)


_REQUESTS_GET = BuiltinTool(
    key="requests_get",
    name="requests_get",
    description="HTTP GET a URL and return the response text. Use for fetching web pages or APIs.",
    parameters=(
        {"name": "url", "type": "str", "required": True, "description": "URL to GET."},
    ),
    imports=(
        "from langchain_community.tools.requests.tool import RequestsGetTool",
        "from langchain_community.utilities.requests import TextRequestsWrapper",
    ),
    ctor="RequestsGetTool(requests_wrapper=TextRequestsWrapper(), allow_dangerous_requests=True)",
)


_REQUESTS_POST = BuiltinTool(
    key="requests_post",
    name="requests_post",
    description="HTTP POST a URL with a JSON body and return the response text.",
    parameters=(
        {"name": "url", "type": "str", "required": True, "description": "URL to POST."},
        {"name": "data", "type": "dict", "required": True, "description": "JSON body to send."},
    ),
    imports=(
        "from langchain_community.tools.requests.tool import RequestsPostTool",
        "from langchain_community.utilities.requests import TextRequestsWrapper",
    ),
    ctor="RequestsPostTool(requests_wrapper=TextRequestsWrapper(), allow_dangerous_requests=True)",
)


_BASH_SHELL = BuiltinTool(
    key="bash_shell",
    name="bash_shell",
    description=(
        "Run a bash command on the server and return stdout+stderr. "
        "DANGEROUS — only include in agents that explicitly need shell "
        "access and are running in a sandboxed environment."
    ),
    parameters=(
        {"name": "commands", "type": "list", "required": True, "description": "Shell commands to run."},
    ),
    imports=("from langchain_community.tools import ShellTool",),
    ctor="ShellTool()",
)


_READ_FILE = BuiltinTool(
    key="read_file",
    name="read_file",
    description="Read the contents of a file from the local filesystem.",
    parameters=(
        {"name": "file_path", "type": "str", "required": True, "description": "Path to the file."},
    ),
    imports=("from langchain_community.tools.file_management.read import ReadFileTool",),
    ctor="ReadFileTool()",
)


_WRITE_FILE = BuiltinTool(
    key="write_file",
    name="write_file",
    description="Write text content to a file on the local filesystem (creates or overwrites).",
    parameters=(
        {"name": "file_path", "type": "str", "required": True, "description": "Path to the file."},
        {"name": "text", "type": "str", "required": True, "description": "Content to write."},
        {"name": "append", "type": "bool", "required": False, "description": "Append instead of overwrite.", "default": False},
    ),
    imports=("from langchain_community.tools.file_management.write import WriteFileTool",),
    ctor="WriteFileTool()",
)


_LIST_DIR = BuiltinTool(
    key="list_dir",
    name="list_dir",
    description="List the entries of a directory on the local filesystem.",
    parameters=(
        {"name": "dir_path", "type": "str", "required": False, "description": "Directory to list. Defaults to cwd.", "default": "."},
    ),
    imports=("from langchain_community.tools.file_management.list_dir import ListDirectoryTool",),
    ctor="ListDirectoryTool()",
)


_REGISTRY: dict[str, BuiltinTool] = {
    t.key: t
    for t in [
        _WIKIPEDIA,
        _DDG_SEARCH,
        _TAVILY_SEARCH,
        _PYTHON_REPL,
        _ARXIV,
        _PUBMED,
        _STACKEXCHANGE,
        _YOUTUBE_SEARCH,
        _REQUESTS_GET,
        _REQUESTS_POST,
        _BASH_SHELL,
        _READ_FILE,
        _WRITE_FILE,
        _LIST_DIR,
    ]
}


def list_keys() -> list[str]:
    return sorted(_REGISTRY.keys())


def get(key: str) -> BuiltinTool:
    """Return the tool entry for `key` or raise ValueError."""
    if key not in _REGISTRY:
        raise ValueError(
            f"Unknown builtin tool {key!r}. "
            f"Available: {', '.join(list_keys())}"
        )
    return _REGISTRY[key]


def to_catalog_entry(key: str) -> dict[str, Any]:
    """Return a catalog dict for a builtin."""
    t = get(key)
    return {
        "name": t.name,
        "source": f"builtin:{t.key}",
        "description": t.description,
        "parameters": list(t.parameters),
        "imports": list(t.imports),
        "ctor": t.ctor,
    }
