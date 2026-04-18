"""Read/write the langosh-agents `langgraph.json` registry.

Each entry maps `graph_id → "module:variable"` (LangGraph Platform convention).
The langosh CLI uses this to scaffold and remove graphs; the langosh-server
loads it at boot to register graphs.
"""

import json
from pathlib import Path

from ..settings import get_agents_path

LANGGRAPH_JSON_NAME = "langgraph.json"


def langgraph_json_path() -> Path:
    return get_agents_path() / LANGGRAPH_JSON_NAME


def graphs_dir() -> Path:
    return get_agents_path() / "graphs"


def graph_dir(graph_id: str) -> Path:
    return graphs_dir() / graph_id


def _read() -> dict:
    path = langgraph_json_path()
    if not path.is_file():
        return {"graphs": {}}
    with open(path) as f:
        data = json.load(f)
    data.setdefault("graphs", {})
    return data


def _write(data: dict) -> None:
    path = langgraph_json_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def list_graphs() -> dict[str, str]:
    """Return the graph_id → module-path mapping."""
    return _read()["graphs"]


def get_graph_entry(graph_id: str) -> str | None:
    """Return the module-path string for a graph_id, or None."""
    return _read()["graphs"].get(graph_id)


def add_graph(graph_id: str, module_path: str | None = None) -> None:
    """Register a graph in langgraph.json. Creates the file if needed.

    `module_path` defaults to `graphs.<id>:graph` (the convention generated
    code follows).
    """
    data = _read()
    data["graphs"][graph_id] = module_path or f"graphs.{graph_id}:graph"
    _write(data)


def remove_graph(graph_id: str) -> bool:
    """Remove a graph from langgraph.json. Returns True if it was present."""
    data = _read()
    if graph_id not in data["graphs"]:
        return False
    del data["graphs"][graph_id]
    _write(data)
    return True
