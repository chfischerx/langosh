# langosh

A CLI tool built with [Typer](https://typer.tiangolo.com/) and [Rich](https://rich.readthedocs.io/).

## Requirements

- Python 3.11+

## Installation

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Usage

```sh
langosh --help
```

### Commands

#### `hello`

Greet someone with style.

```sh
langosh hello              # Hello, World!
langosh hello Claude       # Hello, Claude!
langosh hello Claude -c 3  # greet 3 times
```

#### `version`

Show the application version.

```sh
langosh version
```

## Development

```sh
source .venv/bin/activate
pip install -e .
```

## Project Structure

```
src/
  langosh/
    __init__.py
    main.py                    # CLI entrypoint and REPL
    repl.py                    # Interactive loop with mode system
    state.py / settings.py / config.py
    commands/
      typer_cmds.py            # Registered typer commands
      slash_handlers.py        # /create, /compile, /test, /edit, /select, ...
      menus.py                 # Command menus per mode
    llm/
      providers.py             # Multi-provider LLM dispatch
      model_catalog.py         # Dynamic model discovery
      prompts/
        builder.py             # Builder system prompt (tool list is dynamic)
      tools/                   # CLI-side tool implementations (for /code mode)
    agents/
      builder.py               # /create — LLM produces definition.json
      codegen.py               # /compile — definition.json -> __init__.py
      tool_catalog.py          # Loads tool manifest from langosh-agents
      registry.py              # langgraph.json read/write
      editor.py                # /edit — multi-turn LLM edit loop
      server_client.py         # HTTP client for langosh-server
pyproject.toml
```

## Agent tools and codegen

The langosh CLI creates and compiles LangGraph agents. Agent tool metadata
comes from the sibling `langosh-agents` repo's `tools/manifest.json`, which
is generated from the actual tool source files
(see [langosh-agents README](../langosh-agents/README.md)).

### How the tool catalog flows

```
langosh-agents/tools/*.py        (source of truth: async functions with type hints + docstrings)
        │
        ▼  scripts/build_manifest.py
langosh-agents/tools/manifest.json  (generated: name, module, params, description)
        │
        ▼  tool_catalog.load_tool_catalog()
langosh CLI                          (reads manifest as pure JSON — no tool imports)
        │
        ├──▶ Builder prompt          (LLM sees tool signatures + parameter details)
        └──▶ Codegen                 (emits import statements + validates args)
```

### Agent types

**Simple agents** (`type: "simple"`) use `create_react_agent` — the LLM
dynamically decides which tools to call at runtime.

**Custom agents** (`type: "custom"`) use `StateGraph` with explicit nodes and
edges. Tools can be used in two ways:

- **`type: "tool"` nodes** — the tool function is called directly as a graph
  node with arguments mapped from state. No LLM involved.
- **`type: "llm"` nodes with `"tools": [...]`** — codegen emits a
  `create_react_agent` sub-agent. The LLM dynamically calls the listed tools,
  then the result is written back to state.

Both paths use the same `async def` functions from `langosh-agents/tools/`.
The manifest provides build-time metadata; the functions' type hints and
docstrings provide runtime metadata (LangGraph derives JSON schemas from them
via langchain's `create_tool` introspection).

## Adding Commands

Define new commands in `src/langosh/main.py`:

```python
@app.command()
def my_command(arg: str = typer.Argument(..., help="Description")) -> None:
    """Command docstring shown in --help."""
    console.print(f"[bold]{arg}[/bold]")
```

For command groups, create a sub-app with `typer.Typer()` and register it via `app.add_typer()`.

## License

MIT
