"""Scaffold a minimal langgraph-agents repository."""

from __future__ import annotations

from pathlib import Path

import langosh.state as state

_LANGGRAPH_JSON = """\
{
  "$schema": "https://langgra.ph/schema.json",
  "dependencies": ["."],
  "graphs": {},
  "env": ".env",
  "image_distro": "wolfi"
}
"""


_ENV_EXAMPLE_TEMPLATE = """\
# Reference for `.env`. Every variable this project may use is listed
# here; the repo-local `.env` is where you actually fill in values.
# langgraph.json's `env: ".env"` loads these at deploy time.

# Default LLM for generated graphs that don't pin their own model.
# Format: <provider>:<model-id>. Provider must be one supported by
# LangChain's init_chat_model — e.g. anthropic, openai, bedrock_converse.
# Bedrock IDs already contain colons, so the provider prefix is MUST.
#   ✓ anthropic:claude-sonnet-4-5-20250929
#   ✓ openai:gpt-4o
#   ✓ bedrock_converse:global.anthropic.claude-sonnet-4-5-20250929-v1:0
#   ✗ global.anthropic.claude-sonnet-4-5-20250929-v1:0   (no provider → fails)
DEFAULT_MODEL={default_model}

# LangSmith tracing — traces for this agent land in this project.
LANGSMITH_PROJECT={name}
# LANGSMITH_API_KEY=

# LLM provider keys (only set the ones you use).
# ANTHROPIC_API_KEY=
# OPENAI_API_KEY=
# AWS_ACCESS_KEY_ID=
# AWS_SECRET_ACCESS_KEY=
# AWS_REGION=

# Tool-specific keys (only set the ones your graphs reference).
# TAVILY_API_KEY=
# BRAVE_SEARCH_API_KEY=
# SERPER_API_KEY=
# BING_SUBSCRIPTION_KEY=
"""


_ENV_TEMPLATE = """\
# Local environment for this agents repo. Git-ignored — never commit.
# See `.env.example` for the full list of variables you can set.

# Default LLM for graphs that don't pin their own. Must be
# `<provider>:<model-id>` — e.g. anthropic:claude-sonnet-4-5-20250929,
# openai:gpt-4o, or bedrock_converse:global.anthropic.claude-...:0.
DEFAULT_MODEL={default_model}

LANGSMITH_PROJECT={name}
LANGSMITH_API_KEY=
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
  "langchain-aws>=0.2",
  "langchain-community>=0.3",
  "langchain-experimental>=0.3",
  "python-dotenv>=1.0",
  "httpx>=0.27",
]

[dependency-groups]
dev = [
  "langgraph-cli[inmem]>=0.4",
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

# Environment / credentials — never commit actual secrets.
.env

# Langosh CLI state — conversation history should stay local, not in git.
.langosh/
**/.history.json
"""


_README = """\
# agents

A LangGraph agents repository, scaffolded by the [Langosh CLI](https://github.com/chfischerx/langosh).

## Structure

- `langgraph.json` — graph registry. Maps graph IDs to Python module paths.
- `graphs/` — one subdirectory per graph. Each graph has a `definition.json`
  (authored by Langosh via the LLM) and an auto-generated `__init__.py`
  (produced by Langosh's compiler via `/compile` or `/deploy`).
- `graphs/example/` — a minimal pre-built starter agent so
  `uv run langgraph dev` works out of the box. Safe to delete once you
  have your own graphs.
- `pyproject.toml` — Python package metadata and dependencies.

## Next steps

1. Edit `.env` — add your `LANGSMITH_API_KEY` and any LLM / tool keys
   your graphs need. See `.env.example` for the full list.
2. `uv sync` to install dependencies.
3. `uv run langgraph dev` — LangGraph dev server boots with the bundled
   `example` graph.
4. Run `langosh` in this directory and use `/graphs /create` to
   generate your own graph with LLM guidance.
5. Iterate with `/select` + free-text edits.
6. `/compile` to emit the runnable Python module.
7. `/deploy` to commit + push the repo so LangGraph Platform /
   LangSmith picks up the new code.

## Tool catalog

Langosh resolves every tool at build time by introspecting
`langchain_community.tools` and `langchain_experimental.tools`. The
deployed graph has no runtime tool-discovery code. Run `/fetchtools` in
Langosh at any time to refresh the cached catalog.

See the [Langosh README](https://github.com/chfischerx/langosh#readme) for the full workflow.
"""


_GRAPHS_INIT = ""  # empty module marker


_EXAMPLE_GRAPH_ID = "example"


def _build_example_definition(default_model: str) -> dict:
    """Build the example graph's JSON definition with the chosen model.

    A minimal simple-ReAct agent with no tools — enough for `langgraph dev`
    to boot. The first `provider:`-prefixed token is split out so
    `init_chat_model` doesn't have to guess (important for Bedrock IDs
    that contain their own colons).
    """
    provider, _, model_id = default_model.partition(":")
    return {
        "type": "simple",
        "system_prompt": "You are a friendly assistant. Answer briefly.",
        "tools": [],
        "context": {
            "model_name": {
                "type": "str",
                "default": model_id or default_model,
            },
            # Empty → let init_chat_model parse the prefix in model_name.
            # Set explicitly (e.g. "bedrock_converse") when model_id itself
            # contains colons.
            "model_provider": {
                "type": "str",
                "default": provider if model_id else "",
            },
            "system_prompt": {
                "type": "str",
                "default": "You are a friendly assistant. Answer briefly.",
            },
        },
    }


def _is_effectively_empty(path: Path) -> bool:
    """True if the directory has no non-hidden entries."""
    for entry in path.iterdir():
        if not entry.name.startswith("."):
            return False
    return True


def _escape_toml(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def init_repo(
    cwd: Path,
    name: str,
    description: str,
    default_model: str = "anthropic:claude-sonnet-4-5-20250929",
) -> None:
    """Scaffold a minimal langgraph-agents repo in `cwd`."""
    # Resolve up-front so comparisons against codegen-produced paths
    # (which call `.resolve()` internally) match — otherwise
    # `init_path.relative_to(cwd)` trips over symlinks on macOS where
    # `/var` is `/private/var`.
    cwd = cwd.resolve()
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
    env_example = _ENV_EXAMPLE_TEMPLATE.format(name=name, default_model=default_model)
    env_file = _ENV_TEMPLATE.format(name=name, default_model=default_model)
    files: dict[str, str] = {
        "langgraph.json": _LANGGRAPH_JSON,
        "pyproject.toml": pyproject,
        ".gitignore": _GITIGNORE,
        ".env.example": env_example,
        ".env": env_file,
        "README.md": _README,
        "graphs/__init__.py": _GRAPHS_INIT,
    }

    written: list[str] = []
    for rel_path, content in files.items():
        target = cwd / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        written.append(rel_path)

    # Emit one example graph so `langgraph dev` has something to serve
    # immediately after `uv sync`. `write_compiled_graph` performs the
    # full compile step — writes `definition.json`, generates the
    # Python module, and drops a `.compile_hash` drift marker — so the
    # graph is ready to run without a follow-up `/compile`.
    from .graphs import codegen, registry
    example_definition = _build_example_definition(default_model)
    example_compiled = False
    try:
        init_path = codegen.write_compiled_graph(
            _EXAMPLE_GRAPH_ID, example_definition, []
        )
        registry.add_graph(_EXAMPLE_GRAPH_ID)
        rel_init = init_path.relative_to(cwd)
        written.append(f"graphs/{_EXAMPLE_GRAPH_ID}/definition.json")
        written.append(str(rel_init))
        written.append(f"graphs/{_EXAMPLE_GRAPH_ID}/.compile_hash")
        example_compiled = True
    except Exception as e:
        state.console.print(
            f"[yellow]Skipped example graph (codegen failed):[/yellow] {e}"
        )

    # Sanity-check: load the generated module so we fail loudly here
    # rather than at `langgraph dev` boot. (Compiles the StateGraph too
    # so any node-wiring bug surfaces now.)
    if example_compiled:
        import importlib
        import importlib.util
        import sys as _sys
        spec = importlib.util.spec_from_file_location(
            f"_langosh_verify.{_EXAMPLE_GRAPH_ID}",
            cwd / "graphs" / _EXAMPLE_GRAPH_ID / "__init__.py",
        )
        try:
            module = importlib.util.module_from_spec(spec)
            # Make sibling imports (like `graphs.<id>`) resolvable.
            _sys.path.insert(0, str(cwd))
            try:
                spec.loader.exec_module(module)
                module.graph.compile()
            finally:
                _sys.path.remove(str(cwd))
        except Exception as e:
            state.console.print(
                f"[yellow]Example graph compiled but failed verification:[/yellow] {e}"
            )
            example_compiled = False

    state.console.print(f"[green]Initialized langgraph-agents repo in {cwd}[/green]")
    for p in written:
        state.console.print(f"  [dim]+[/dim] {p}")
    if example_compiled:
        state.console.print(
            f"  [green]\u2713[/green] [dim]Example graph compiled and "
            f"registered in langgraph.json.[/dim]"
        )
    state.console.print()
    state.console.print("[bold]Next steps:[/bold]")
    state.console.print(
        "  1. Edit [cyan].env[/cyan] — set [cyan]LANGSMITH_API_KEY[/cyan] and any LLM / tool keys your graphs need "
        "([dim].env.example[/dim] lists the full set)"
    )
    state.console.print("  2. [cyan]uv sync[/cyan] — install dependencies")
    state.console.print(
        "  3. [cyan]uv run langgraph dev[/cyan] — boots with the bundled [cyan]example[/cyan] graph"
    )
    state.console.print(
        "  4. [cyan]/graphs[/cyan] [cyan]/create[/cyan] — generate your own graph with LLM guidance"
    )
    state.console.print(
        "  5. [cyan]/compile[/cyan] then [cyan]/deploy[/cyan] — build and push to the server"
    )
