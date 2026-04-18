"""Load the agent-tool catalog from the langosh-agents repo.

The CLI doesn't import agent tool modules (those live in `langosh-agents/tools/`
and may pull optional deps like slack-sdk). It only needs to *describe* them
to the LLM in the builder prompt and *write import statements* against them
in codegen. Both of those are pure data, sourced from
`<agents-path>/tools/manifest.json`.

Single source of truth: run `scripts/build_manifest.py` in langosh-agents to
regenerate the manifest from function signatures and docstrings.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..settings import get_agents_path

_MANIFEST_RELPATH = Path("tools") / "manifest.json"
_REQUIRED_TOOL_FIELDS = ("name", "module", "function", "description", "parameters")
_REQUIRED_PARAM_FIELDS = ("name", "type", "required", "description")


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
    module: str
    function: str
    description: str
    parameters: tuple[ParamSpec, ...] = field(default_factory=tuple)

    @property
    def signature(self) -> str:
        """Render human-readable signature from parameters."""
        parts = []
        for p in self.parameters:
            if p.required:
                parts.append(p.name)
            else:
                parts.append(f"{p.name}={p.default!r}")
        return f"{self.name}({', '.join(parts)})"

    @property
    def param_names(self) -> set[str]:
        """Set of parameter names for quick lookups."""
        return {p.name for p in self.parameters}


_cache: tuple[Path, list[ToolSpec]] | None = None


def manifest_path() -> Path:
    """Absolute path to the catalog manifest."""
    return get_agents_path() / _MANIFEST_RELPATH


def _parse_param(raw: dict, tool_name: str, idx: int, path: Path) -> ParamSpec:
    missing = [f for f in _REQUIRED_PARAM_FIELDS if f not in raw]
    if missing:
        raise ValueError(
            f"Tool '{tool_name}' parameter #{idx} in {path} is missing "
            f"fields: {', '.join(missing)}."
        )
    return ParamSpec(
        name=raw["name"],
        type=raw["type"],
        required=raw["required"],
        description=raw["description"],
        default=raw.get("default"),
    )


def load_tool_catalog() -> list[ToolSpec]:
    """Return the agent tool catalog. Cached per agents-path.

    Raises FileNotFoundError if the manifest is missing, ValueError if it is
    malformed. Both messages name the expected path so the user can act.
    """
    global _cache
    path = manifest_path()
    if _cache is not None and _cache[0] == path:
        return _cache[1]

    if not path.is_file():
        raise FileNotFoundError(
            f"Tool manifest not found at {path}. "
            f"Run `python scripts/build_manifest.py` in the langosh-agents repo."
        )

    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise ValueError(f"Tool manifest at {path} is not valid JSON: {e}") from e

    if not isinstance(raw, list):
        raise ValueError(
            f"Tool manifest at {path} must be a JSON array of tool entries."
        )

    specs: list[ToolSpec] = []
    seen: set[str] = set()
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(
                f"Tool manifest entry #{i} in {path} must be an object."
            )
        missing = [f for f in _REQUIRED_TOOL_FIELDS if f not in entry]
        if missing:
            raise ValueError(
                f"Tool manifest entry #{i} in {path} is missing fields: "
                f"{', '.join(missing)}."
            )
        name = entry["name"]
        if name in seen:
            raise ValueError(
                f"Tool manifest at {path} has duplicate tool name: {name!r}."
            )
        seen.add(name)

        params = tuple(
            _parse_param(p, name, j, path)
            for j, p in enumerate(entry["parameters"])
        )
        specs.append(
            ToolSpec(
                name=name,
                module=entry["module"],
                function=entry["function"],
                description=entry["description"],
                parameters=params,
            )
        )

    _cache = (path, specs)
    return specs


def invalidate_cache() -> None:
    """Drop the cached catalog. Call after switching agents-path at runtime."""
    global _cache
    _cache = None
