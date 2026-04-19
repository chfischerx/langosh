"""Build the tool catalog.

Entry point: `fetch_catalog()` — runs the two discovery paths, merges
them, writes the cache, returns a summary.

Sources:
  1. **Curated** — hand-tuned registry in `builtin_tools.py`. Hand-written
     descriptions, handles special ctor args. Wins on name collisions.
  2. **Community** — introspection of `langchain_community.tools` +
     `langchain_experimental.tools` via `tool_discovery.py`. Best-effort:
     only tools whose ctor matches a supported pattern (zero-arg or
     api_wrapper) are included.

No runtime tool discovery happens in the generated graph module: every
tool the builder can reference has a static import + ctor; codegen
emits both directly.

mcp.json `builtins`:
  - Omitted (or file absent) → include every discovered + curated tool.
  - Provided → filter the merged catalog to that list of names.
"""

from __future__ import annotations

import langosh.state as state

from ..settings import get_agents_path
from . import builtin_tools, tool_cache, tool_discovery
from .mcp_config import load_mcp_config


def _curated_entries() -> list[dict]:
    return [builtin_tools.to_catalog_entry(key) for key in builtin_tools.list_keys()]


def _merge(curated: list[dict], discovered: list[dict]) -> list[dict]:
    """Curated wins on name collisions. Discovered fills in the long tail."""
    out: list[dict] = list(curated)
    seen = {e["name"] for e in out}
    for e in discovered:
        if e["name"] in seen:
            continue
        seen.add(e["name"])
        out.append(e)
    return out


def _filter_by_builtins(catalog: list[dict], filter_names: list[str]) -> list[dict]:
    """Keep only entries whose name is in `filter_names`. Warn on unknowns."""
    names = set(filter_names)
    kept = [e for e in catalog if e["name"] in names]
    missing = names - {e["name"] for e in kept}
    if missing:
        state.console.print(
            f"[yellow]mcp.json references unknown tools:[/yellow] "
            f"{', '.join(sorted(missing))}"
        )
    return kept


def _group_summary(catalog: list[dict]) -> dict[str, list[str]]:
    """Group entries by source prefix (builtin / community / experimental)."""
    out: dict[str, list[str]] = {}
    for entry in catalog:
        prefix = entry["source"].split(":", 1)[0]
        out.setdefault(prefix, []).append(entry["name"])
    return out


def fetch_catalog() -> dict:
    """Resolve curated + discovered tools, write the cache, return summary."""
    curated = _curated_entries()
    try:
        discovered = tool_discovery.discover_tools()
    except Exception as e:
        state.console.print(
            f"[yellow]Tool discovery failed, using curated only:[/yellow] {e}"
        )
        discovered = []

    catalog = _merge(curated, discovered)

    cfg = load_mcp_config()
    if cfg.builtins is not None:
        catalog = _filter_by_builtins(catalog, cfg.builtins)

    agents_path = get_agents_path()
    tool_cache.write_cache(agents_path, catalog)

    return {
        "agents_path": str(agents_path),
        "total": len(catalog),
        "curated": len(curated),
        "discovered": len(discovered),
        "by_source": _group_summary(catalog),
    }
