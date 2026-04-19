"""Unified tool catalog sourced from curated LangChain builtins.

Entries live on disk in a cache populated by `/fetchtools`. The builder
prompt and codegen both read through `load_tool_catalog()`.

Every tool in the catalog is statically resolvable at build time —
`imports` + `ctor` get emitted directly into the compiled graph module.
No runtime discovery happens in the generated code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..settings import get_agents_path
from . import tool_cache


@dataclass(frozen=True)
class ParamSpec:
    name: str
    type: str
    required: bool
    description: str
    default: Any = None


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    source: str  # "builtin:<key>"
    parameters: tuple[ParamSpec, ...] = field(default_factory=tuple)
    imports: tuple[str, ...] = field(default_factory=tuple)
    ctor: str = ""

    @property
    def signature(self) -> str:
        parts = []
        for p in self.parameters:
            if p.required:
                parts.append(p.name)
            else:
                parts.append(f"{p.name}={p.default!r}")
        return f"{self.name}({', '.join(parts)})"

    @property
    def param_names(self) -> set[str]:
        return {p.name for p in self.parameters}

    @property
    def is_builtin(self) -> bool:
        return self.source.startswith("builtin:")


def _parse_param(raw: dict) -> ParamSpec:
    return ParamSpec(
        name=raw["name"],
        type=raw.get("type", "str"),
        required=bool(raw.get("required", False)),
        description=raw.get("description", ""),
        default=raw.get("default"),
    )


def _entry_to_spec(entry: dict) -> ToolSpec:
    params = tuple(_parse_param(p) for p in entry.get("parameters", []))
    return ToolSpec(
        name=entry["name"],
        description=entry.get("description", ""),
        source=entry.get("source", ""),
        parameters=params,
        imports=tuple(entry.get("imports") or []),
        ctor=entry.get("ctor", ""),
    )


def load_tool_catalog() -> list[ToolSpec]:
    """Return the cached catalog.

    If the cache is missing, returns an empty list. The builder prompt
    shows a hint to run `/fetchtools`; codegen raises a clear error
    when an unknown tool is referenced.
    """
    agents_path = get_agents_path()
    raw = tool_cache.read_cache(agents_path)
    if raw is None:
        return []
    return [_entry_to_spec(entry) for entry in raw]


def invalidate_cache() -> None:
    """Drop the on-disk cache so the next build/compile re-fetches."""
    tool_cache.invalidate(get_agents_path())
