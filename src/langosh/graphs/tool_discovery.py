"""Introspect LangChain community/experimental tool packages at build time.

Walks `langchain_community.tools` and `langchain_experimental.tools`, finds
every `BaseTool` subclass, and derives the static import + ctor expression
needed to instantiate it on the server.

Two constructor patterns are recognized:
  1. Zero-arg — every field of the class has a default (or is optional).
     → ctor = "ClassName()"
  2. api_wrapper — the single required field is `api_wrapper`, and a
     matching `XxxAPIWrapper` (or `XxxWrapper`) exists in
     `langchain_community.utilities`.
     → ctor = "ClassName(api_wrapper=XxxAPIWrapper())"

Tools that need other required args (API keys passed as ctor args,
specific client objects, etc.) are skipped — the builder can't fill
those in blindly. The curated registry in `builtin_tools.py` covers
those cases with hand-tuned entries.

Results are merged into the catalog by `tool_fetcher.py`. Curated entries
win on name collisions (they carry richer descriptions and handle
special ctor args like `allow_dangerous_requests=True`).
"""

from __future__ import annotations

import inspect
import os
import warnings
from typing import Any

_CTOR_TRIM_SUFFIXES = (
    "QueryRun",
    "SearchResults",
    "SearchRun",
    "Search",
    "Run",
    "Tool",
)

_UTILITY_SUFFIXES = ("APIWrapper", "SearchAPIWrapper", "Wrapper")


def _required_fields(cls) -> list[str]:
    """Return names of required pydantic fields on `cls`."""
    fields = getattr(cls, "model_fields", None) or {}
    return [name for name, info in fields.items() if info.is_required()]


def _field_default(cls, name: str) -> Any:
    fields = getattr(cls, "model_fields", None) or {}
    info = fields.get(name)
    if info is None:
        return None
    default = info.default
    # PydanticUndefined has a distinctive repr
    if repr(default) == "PydanticUndefined":
        return None
    return default


def _infer_name(cls) -> str:
    name = _field_default(cls, "name")
    if isinstance(name, str) and name:
        return name
    return cls.__name__


def _infer_description(cls) -> str:
    desc = _field_default(cls, "description")
    if isinstance(desc, str) and desc:
        return desc.strip().split("\n")[0]
    doc = (cls.__doc__ or "").strip()
    return doc.split("\n")[0] if doc else ""


def _infer_params(cls) -> list[dict]:
    """Extract parameter entries from the tool's args_schema (or fallback)."""
    schema_cls = _field_default(cls, "args_schema")
    if schema_cls is None or not hasattr(schema_cls, "model_fields"):
        # BaseTool default single-input: a string query.
        return [{
            "name": "query",
            "type": "str",
            "required": True,
            "description": "Input for the tool.",
        }]
    out: list[dict] = []
    for fname, finfo in schema_cls.model_fields.items():
        ann = finfo.annotation
        type_str = getattr(ann, "__name__", None) or str(ann)
        out.append({
            "name": fname,
            "type": type_str,
            "required": finfo.is_required(),
            "description": (finfo.description or "")[:200],
        })
    return out


def _find_utility(cls_name: str, utilities: dict[str, type]) -> str | None:
    """Find a matching utility class name for an api_wrapper ctor."""
    base = cls_name
    for suf in _CTOR_TRIM_SUFFIXES:
        if base.endswith(suf):
            base = base[: -len(suf)]
            break
    for suf in _UTILITY_SUFFIXES:
        key = base + suf
        if key in utilities:
            return key
    return None


def _resolve_ctor(cls, utilities: dict[str, type]) -> tuple[list[str], str] | None:
    """Return (imports, ctor_expr) or None if the ctor can't be derived."""
    required = _required_fields(cls)
    module = cls.__module__
    cls_name = cls.__name__

    if not required:
        imports = [f"from {module} import {cls_name}"]
        return imports, f"{cls_name}()"

    if required == ["api_wrapper"]:
        util_name = _find_utility(cls_name, utilities)
        if util_name is None:
            return None
        util_cls = utilities[util_name]
        imports = [
            f"from {module} import {cls_name}",
            f"from {util_cls.__module__} import {util_name}",
        ]
        ctor = f"{cls_name}(api_wrapper={util_name}())"
        return imports, ctor

    return None


def _load_utilities() -> dict[str, type]:
    """Return a map of utility class name → class from langchain_community.utilities."""
    try:
        import langchain_community.utilities as umod
    except ImportError:
        return {}
    out: dict[str, type] = {}
    for name in getattr(umod, "__all__", []):
        try:
            obj = getattr(umod, name)
        except Exception:
            continue
        if inspect.isclass(obj):
            out[name] = obj
    return out


def _iter_tool_classes(module) -> list[type]:
    """Yield BaseTool subclasses re-exported from `module.__all__`."""
    try:
        from langchain_core.tools import BaseTool
    except ImportError:
        return []
    out: list[type] = []
    for name in getattr(module, "__all__", []):
        try:
            obj = getattr(module, name)
        except Exception:
            continue
        if inspect.isclass(obj) and issubclass(obj, BaseTool) and obj is not BaseTool:
            out.append(obj)
    return out


def _discover_from_module(module_path: str, source_prefix: str, utilities: dict[str, type]) -> list[dict]:
    """Discover tools in a single root module (e.g. `langchain_community.tools`)."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            module = __import__(module_path, fromlist=["*"])
    except ImportError:
        return []

    entries: list[dict] = []
    for cls in _iter_tool_classes(module):
        resolved = _resolve_ctor(cls, utilities)
        if resolved is None:
            continue
        imports, ctor = resolved
        submod = cls.__module__.removeprefix(module_path + ".")
        entries.append({
            "name": _infer_name(cls),
            "source": f"{source_prefix}:{submod}",
            "description": _infer_description(cls),
            "parameters": _infer_params(cls),
            "imports": imports,
            "ctor": ctor,
        })
    return entries


def discover_tools() -> list[dict]:
    """Return catalog entries for every discoverable LangChain tool.

    Skips tools whose constructor signatures don't match the two supported
    patterns (zero-arg, api_wrapper). Descriptions come from the class
    definition; the server-side pip package provides the actual runtime.
    """
    os.environ.setdefault("USER_AGENT", "langosh-cli/0.1.0")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        utilities = _load_utilities()
        entries = _discover_from_module(
            "langchain_community.tools", "community", utilities
        )
        entries.extend(
            _discover_from_module(
                "langchain_experimental.tools", "experimental", utilities
            )
        )
    return entries
