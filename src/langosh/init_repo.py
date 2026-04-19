"""Scaffold a minimal langgraph-agents repository."""

from __future__ import annotations

from pathlib import Path

import langosh.state as state


_LANGGRAPH_JSON = """\
{
  "dependencies": ["."],
  "graphs": {}
}
"""


_PYPROJECT_TOML_TEMPLATE = """\
[project]
name = "{name}"
version = "0.1.0"
description = "{description}"
requires-python = ">=3.11"
dependencies = [
  "langgraph>=1.0",
  "langchain>=1.0",
  "langchain-anthropic>=1.0",
  "langchain-openai>=0.3",
  "langchain-community>=0.3",
  "langchain-experimental>=0.3",
  "httpx>=0.27",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["graphs"]
"""


_GITIGNORE = """\
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
.venv/
.pytest_cache/
.ruff_cache/
*.compile_hash
.DS_Store
"""


_README = """\
# agents

A LangGraph agents repository, scaffolded by the [Langosh CLI](../langosh-cli).

## Structure

- `langgraph.json` — graph registry. Maps graph IDs to Python module paths.
- `graphs/` — one subdirectory per graph. Each graph has a `definition.json`
  (authored by Langosh via the LLM) and an auto-generated `__init__.py`
  (produced by Langosh's compiler via `/compile` or `/deploy`).
- `pyproject.toml` — Python package metadata and dependencies.

## Next steps

1. Run `langosh` in this directory.
2. Use `/graphs /create` to generate your first graph with LLM guidance.
3. Iterate with `/select` + free-text edits.
4. `/compile` to emit the runnable Python module.
5. `/deploy` to push the repo and hot-reload the server.

## Tool catalog

Langosh resolves every tool at build time by introspecting
`langchain_community.tools` and `langchain_experimental.tools`. The
deployed graph has no runtime tool-discovery code. Run `/fetchtools` in
Langosh at any time to refresh the cached catalog.

See the [Langosh README](../langosh-cli/README.md) for the full workflow.
"""


_GRAPHS_INIT = ""  # empty module marker


def _is_effectively_empty(path: Path) -> bool:
    """True if the directory has no non-hidden entries."""
    for entry in path.iterdir():
        if not entry.name.startswith("."):
            return False
    return True


def _escape_toml(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def init_repo(cwd: Path, name: str, description: str) -> None:
    """Scaffold a minimal langgraph-agents repo in `cwd`."""
    if not cwd.is_dir():
        raise RuntimeError(f"Not a directory: {cwd}")

    if not _is_effectively_empty(cwd):
        raise RuntimeError(
            f"Refusing to scaffold: directory is not empty: {cwd}. "
            "Run /initrepo in an empty directory."
        )

    pyproject = _PYPROJECT_TOML_TEMPLATE.format(
        name=_escape_toml(name),
        description=_escape_toml(description),
    )
    files: dict[str, str] = {
        "langgraph.json": _LANGGRAPH_JSON,
        "pyproject.toml": pyproject,
        ".gitignore": _GITIGNORE,
        "README.md": _README,
        "graphs/__init__.py": _GRAPHS_INIT,
    }

    written: list[str] = []
    for rel_path, content in files.items():
        target = cwd / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        written.append(rel_path)

    state.console.print(f"[green]Initialized langgraph-agents repo in {cwd}[/green]")
    for p in written:
        state.console.print(f"  [dim]+[/dim] {p}")
    state.console.print()
    state.console.print("[bold]Next steps:[/bold]")
    state.console.print("  1. [cyan]/graphs[/cyan] — enter graph development mode")
    state.console.print("  2. [cyan]/create[/cyan] — generate your first graph with LLM guidance")
    state.console.print(
        "  3. [cyan]/compile[/cyan] then [cyan]/deploy[/cyan] — build and push to the server"
    )
