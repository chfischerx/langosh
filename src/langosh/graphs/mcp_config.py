"""Read mcp.json from the agents-repo root.

Despite the historical filename, this config no longer drives any MCP
client. It simply lists which curated LangChain builtins the graph
exposes. All resolution happens at build time inside the Langosh CLI;
the generated graph module has no runtime tool discovery.

If `builtins` is omitted (or mcp.json is absent entirely), the fetcher
falls back to "include every curated builtin".
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..settings import get_agents_path

_FILENAME = "mcp.json"


@dataclass(frozen=True)
class McpConfig:
    """Parsed `mcp.json`."""

    builtins: list[str] | None = field(default=None)


def mcp_config_path() -> Path:
    return get_agents_path() / _FILENAME


def load_mcp_config() -> McpConfig:
    """Read mcp.json. Returns an empty config if the file doesn't exist."""
    path = mcp_config_path()
    if not path.is_file():
        return McpConfig()
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise ValueError(f"mcp.json at {path} is not valid JSON: {e}") from e
    if not isinstance(raw, dict):
        raise ValueError(f"mcp.json at {path} must be a JSON object.")
    builtins = raw.get("builtins")
    if builtins is None:
        return McpConfig(builtins=None)
    if not isinstance(builtins, list):
        raise ValueError("mcp.json `builtins` must be an array.")
    return McpConfig(builtins=[str(x) for x in builtins])
