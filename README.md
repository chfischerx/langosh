# langosh

A CLI to create, test, and deploy LangGraph agents.

## Requirements

- Python 3.11+
- A running [langosh-server](../langosh-server) instance
- The [langosh-agents](../langosh-agents) repo (sibling directory)

## Installation

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Usage

```sh
langosh
```

The CLI starts in **main mode** (agent management). Type `/` to see available
commands with tab completion, or use arrow keys to recall input history.

## Modes

| Mode | Purpose | Enter with |
|------|---------|------------|
| **main** | Manage graphs, assistants, threads, runs | default on startup |
| **chat** | Direct LLM conversation | `/chat` |
| **code** | LLM with tool use (file read/write/exec) | `/code` |
| **admin** | Server configuration and management | `/admin` |
| **edit** | Edit a graph via LLM conversation | `/edit` (with graph selected) |

Use `/home` to return to main mode from any other mode.

## Commands

### Main mode — no graph selected

| Command | Description |
|---------|-------------|
| `/list` | List graphs in langgraph.json |
| `/select` | Select a graph and assistant |
| `/create` | Create a new graph (LLM-generated) |
| `/deploy` | Commit, push, and reload agents on the server |
| `/chat` | Switch to LLM chat mode |
| `/code` | Switch to LLM code mode (with tools) |
| `/admin` | Switch to server admin mode |
| `/models` | List/filter models |
| `/use` | Select a model |
| `/version` | Show the application version |
| `/help` | Show available commands |
| `/exit` | Quit |

### Main mode — graph selected

#### Running agents

| Command | Description |
|---------|-------------|
| `/run` | Run on the server (streaming, in thread) |
| `/runwait` | Run and wait for result (no streaming, in thread) |
| `/runsl` | Stateless run (streaming, no thread history) |
| `/runslwait` | Stateless run and wait (no streaming, no thread) |
| `/runs` | List recent runs for the active thread |

`/run` and `/runwait` are conversational — messages are stored in the active
thread and the agent has access to previous turns. `/runsl` and `/runslwait`
are stateless — each invocation is independent with no memory.

#### Graph management

| Command | Description |
|---------|-------------|
| `/edit` | Edit selected graph (LLM conversation; regen on save) |
| `/compile` | Regenerate `__init__.py` from `definition.json` |
| `/graph` | Visualize the selected graph |
| `/delete` | Delete this graph + langgraph.json entry |
| `/select` | Switch to a different graph |
| `/create` | Create a new graph |

#### Assistants

| Command | Description |
|---------|-------------|
| `/assistants` | List assistants for the selected graph |
| `/assistant create` | Create a new assistant with custom context |
| `/assistant update` | Update the active assistant's context |
| `/assistant delete` | Delete an assistant |

#### Threads

| Command | Description |
|---------|-------------|
| `/threads` | List threads — switch to a previous conversation |
| `/thread` | Show current thread info and conversation |
| `/thread new` | Start a new thread (keeps previous) |
| `/thread delete` | Delete a thread |
| `/clc` | Reset the active thread (deletes and creates new) |

#### Git and deploy

| Command | Description |
|---------|-------------|
| `/deploy` | Commit, push, and reload agents on the server |
| `/status` | Show git status (in agents repo) |
| `/commit` | Commit all changes (in agents repo) |

### Chat mode

| Command | Description |
|---------|-------------|
| `/models` | List/filter models |
| `/search` | Fuzzy search for models |
| `/fetchmodels` | Refresh model list from APIs |
| `/use` | Select a model |
| `/debug` | Inspect last LLM request/response |
| `/cls` | Clear screen |
| `/clc` | Clear conversation history |
| `/code` | Switch to code mode |
| `/home` | Return to home |

Any text that doesn't start with `/` is sent as an LLM prompt.

### Code mode

| Command | Description |
|---------|-------------|
| `/plan` | Approve every tool call |
| `/auto` | Auto-approve reads, approve writes |
| `/edit` | Auto-approve all tool calls |
| `/models` | List/filter models |
| `/search` | Fuzzy search for models |
| `/fetchmodels` | Refresh model list from APIs |
| `/use` | Select a model |
| `/debug` | Inspect last LLM request/response |
| `/cls` | Clear screen |
| `/clc` | Clear conversation history |
| `/chat` | Switch to chat mode |
| `/home` | Return to home |

Any text that doesn't start with `/` is sent as a coding task with tool access.

### Edit mode

Available after `/edit` on a selected graph.

| Command | Description |
|---------|-------------|
| `/plan` | Approve every tool call |
| `/auto` | Auto-approve reads, approve writes |
| `/run` | Run the graph in the active thread |
| `/debug` | Inspect last LLM request/response |
| `/cls` | Clear screen |
| `/clc` | Reset the active thread |
| `/done` | Exit edit mode |

Any text that doesn't start with `/` is sent as an edit instruction.

### Admin mode

| Command | Description |
|---------|-------------|
| `/server` | Show or set the langosh-server URL |
| `/info` | Show server info (version, graphs, status) |
| `/reload` | Hot-reload agents on the server |
| `/config` | View and edit server configuration |
| `/keys` | List API keys |
| `/key create` | Create an API key |
| `/key delete` | Delete an API key |
| `/key rotate` | Rotate an API key |
| `/home` | Return to home |

#### /config

The `/config` command provides an interactive menu:

- **Show all config** — display all parameters grouped by category
- **Setup wizard** — step through every parameter sequentially
- **Reset all config** — clear all values (revert to env-var fallbacks)
- **Category selection** — pick a category, then a parameter to set or clear

Categories: `model`, `provider`, `tools`, `tracing`, `git`, `auth`.
Encrypted values (API keys, tokens) use masked input.

## Project structure

```
src/langosh/
  main.py                    # CLI entrypoint and REPL
  repl.py                    # Interactive loop with mode system
  input.py                   # Prompt toolkit input with completion + history
  state.py                   # Shared mutable state, Rich console with theme
  settings.py / config.py    # Settings and configuration
  commands/
    typer_cmds.py            # Registered typer commands (/models, /use, /search)
    slash_handlers.py        # All slash command handlers
    menus.py                 # Command menus per mode
  llm/
    providers.py             # Multi-provider LLM dispatch
    model_catalog.py         # Dynamic model discovery
    prompts/
      builder.py             # Builder system prompt (tool list from manifest)
    tools/                   # CLI-side tool implementations (for /code mode)
  agents/
    builder.py               # /create — LLM produces definition.json
    codegen.py               # /compile — definition.json -> __init__.py
    editor.py                # /edit — multi-turn LLM edit loop
    tool_catalog.py          # Loads tool manifest from langosh-agents
    registry.py              # langgraph.json read/write
    server_client.py         # HTTP client for langosh-server
```

## Agent tools and codegen

The langosh CLI creates and compiles LangGraph agents. Agent tool metadata
comes from the sibling `langosh-agents` repo's `tools/manifest.json`, which
is generated from the actual tool source files
(see [langosh-agents README](../langosh-agents/README.md)).

### How the tool catalog flows

```
langosh-agents/tools/*.py        (source of truth: async functions with type hints + docstrings)
        |
        v  scripts/build_manifest.py
langosh-agents/tools/manifest.json  (generated: name, module, params, description)
        |
        v  tool_catalog.load_tool_catalog()
langosh CLI                          (reads manifest as pure JSON — no tool imports)
        |
        +-->  Builder prompt          (LLM sees tool signatures + parameter details)
        +-->  Codegen                 (emits import statements + validates args)
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

## License

MIT
