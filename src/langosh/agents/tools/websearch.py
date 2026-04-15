"""Web search tool for LangGraph agents — supports multiple search providers."""

import asyncio
import logging
import os

logger = logging.getLogger(__name__)


async def _search_tavily(query: str, max_results: int, include_raw_content: bool) -> str:
    """Search using Tavily API."""
    try:
        from tavily import TavilyClient
    except ImportError:
        return "Error: tavily-python not installed. Run: pip install tavily-python"

    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        return "Error: TAVILY_API_KEY not set in environment."

    def _search():
        client = TavilyClient(api_key=api_key)
        return client.search(
            query=query,
            max_results=max_results,
            include_raw_content=include_raw_content,
        )

    response = await asyncio.to_thread(_search)
    return _format_results(response.get("results", []))


async def _search_serper(query: str, max_results: int, include_raw_content: bool) -> str:
    """Search using Serper (Google Search API)."""
    try:
        import httpx
    except ImportError:
        return "Error: httpx not installed."

    api_key = os.environ.get("SERPER_API_KEY", "")
    if not api_key:
        return "Error: SERPER_API_KEY not set in environment."

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": query, "num": max_results},
        )
        resp.raise_for_status()
        data = resp.json()

    results = []
    for item in data.get("organic", [])[:max_results]:
        results.append({
            "title": item.get("title", ""),
            "url": item.get("link", ""),
            "content": item.get("snippet", ""),
        })
    return _format_results(results)


async def _search_brave(query: str, max_results: int, include_raw_content: bool) -> str:
    """Search using Brave Search API."""
    try:
        import httpx
    except ImportError:
        return "Error: httpx not installed."

    api_key = os.environ.get("BRAVE_API_KEY", "")
    if not api_key:
        return "Error: BRAVE_API_KEY not set in environment."

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
            params={"q": query, "count": max_results},
        )
        resp.raise_for_status()
        data = resp.json()

    results = []
    for item in data.get("web", {}).get("results", [])[:max_results]:
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "content": item.get("description", ""),
        })
    return _format_results(results)


def _format_results(results: list[dict]) -> str:
    """Format search results into a readable string."""
    if not results:
        return "No results found."

    parts = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "Untitled")
        url = r.get("url", "")
        content = r.get("content", r.get("snippet", ""))
        parts.append(f"{i}. {title}\n   {url}\n   {content}")
    return "\n\n".join(parts)


_PROVIDERS = {
    "tavily": _search_tavily,
    "serper": _search_serper,
    "brave": _search_brave,
}


def _detect_provider() -> str:
    """Auto-detect search provider from available API keys."""
    if os.environ.get("TAVILY_API_KEY"):
        return "tavily"
    if os.environ.get("SERPER_API_KEY"):
        return "serper"
    if os.environ.get("BRAVE_API_KEY"):
        return "brave"
    return "tavily"  # default


async def web_search(
    query: str,
    max_results: int = 5,
    include_raw_content: bool = False,
    provider: str = "",
) -> str:
    """Search the internet for information.

    Args:
        query: Search query
        max_results: Maximum number of results to return
        include_raw_content: Whether to include raw page content
        provider: Search provider ('tavily', 'serper', 'brave'). Auto-detected if empty.
    """
    provider = provider or _detect_provider()
    search_fn = _PROVIDERS.get(provider)
    if not search_fn:
        return f"Error: Unknown search provider '{provider}'. Available: {', '.join(_PROVIDERS)}"
    return await search_fn(query, max_results, include_raw_content)
