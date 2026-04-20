"""Build the tool catalog.

Entry point: `fetch_catalog()` — runs discovery against
`langchain_community.tools` + `langchain_experimental.tools`, writes the
cache, returns a summary. Hand-tuned overrides for specific tools live in
`tool_discovery._OVERRIDES`.

No runtime tool discovery happens in the generated graph module: every
tool the builder can reference has a static import + ctor; codegen
emits both directly.
"""

from __future__ import annotations

import langosh.state as state

from ..settings import get_agents_path
from . import tool_cache, tool_discovery


def _group_summary(catalog: list[dict]) -> dict[str, list[str]]:
    """Group entries by source prefix (community / experimental)."""
    out: dict[str, list[str]] = {}
    for entry in catalog:
        prefix = entry["source"].split(":", 1)[0]
        out.setdefault(prefix, []).append(entry["name"])
    return out


def fetch_catalog() -> dict:
    """Discover tools, write the cache, return a summary dict."""
    try:
        catalog = tool_discovery.discover_tools()
    except Exception as e:
        state.console.print(f"[bold red]Tool discovery failed:[/bold red] {e}")
        catalog = []

    agents_path = get_agents_path()
    tool_cache.write_cache(agents_path, catalog)

    return {
        "agents_path": str(agents_path),
        "total": len(catalog),
        "by_source": _group_summary(catalog),
    }
