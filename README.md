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

The CLI starts in **main mode**. Type `/` to see available commands with tab
completion, or use arrow keys to recall input history.

## Navigation

The CLI uses a hierarchical mode system. Each mode has its own commands.

- `/back` — go back to the parent mode
- `/home` — return to main mode
- `/help` — show available commands for the current mode
- `/cls` — clear screen
- `/exit` — quit

The mode bar at the top shows the current path (e.g. `exec[local]:my-graph:assistant-1`).

## Mode tree

```
main
├── dev                      Local graph development
│   └── [graph_id]:[mode]    LLM-driven editing (normal/plan/auto)
├── exec[server]             Execute graphs on a server
│   └── [graph_id]           Graph commands
│       └── [assistant]      Assistant commands
│           └── [thread]     Thread inspection
│               └── [run]    Run inspection
├── llm                      LLM interaction
│   ├── chat                 Direct conversation
│   └── code                 LLM with tool use
├── server                   Server management
│   └── [server_name]        Selected server
│       ├── config           Server configuration
│       └── apikeys          API key management
└── settings                 CLI settings
```

## Commands

### Main (`main`)

| Command | Description |
|---------|-------------|
| `/dev` | Graph development mode |
| `/exec` | Execute graphs and assistants |
| `/llm` | LLM chat and code mode |
| `/server` | Server management |
| `/settings` | CLI settings |
| `/version` | Show the application version |

### Dev (`dev`)

Requires the CLI to be started within a langgraph code repository.

| Command | Description |
|---------|-------------|
| `/list` | List all graphs from the current repo |
| `/select` | Select an existing graph to work with |
| `/create` | Create a new graph with LLM guidance |
| `/status` | Show git status |
| `/commit` | Commit all changes |

### Dev > Graph (`dev:[graph_id]:[mode]`)

LLM-driven editing. Free text is sent as edit instructions.

| Command | Description |
|---------|-------------|
| `/normal` | Confirm every destructive operation |
| `/plan` | Read-only tools, no edits |
| `/auto` | Auto-approve all tool calls |
| `/compile` | Compile the selected graph |
| `/delete` | Delete the selected graph |
| `/preview` | Visualize the selected graph |
| `/status` | Show git status |
| `/commit` | Commit all changes |

### Exec (`exec[server]`)

Requires a selected server.

| Command | Description |
|---------|-------------|
| `/list` | List all available graphs (from server) |
| `/select` | Select a graph |
| `/deploy` | Commit, push, and reload agents on the server |

### Exec > Graph (`exec[server]:[graph_id]`)

| Command | Description |
|---------|-------------|
| `/select` | Select an assistant |
| `/thread` | Select a thread |
| `/create` | Create a new assistant with custom context |
| `/search` | Search for assistants |
| `/show` | Display the graph (ASCII diagram from server) |
| `/test` | Stateless run (no thread history) |
| `/run` | Create a stateful run (interactive: mode, thread, message) |
| `/threads` | List all threads (filtered by graph) |
| `/delthread` | Delete a thread |
| `/delallthreads` | Delete all threads (filtered by graph) |

### Exec > Assistant (`exec[server]:[graph_id]:[assistant]`)

| Command | Description |
|---------|-------------|
| `/thread` | Select a thread |
| `/show` | Display assistant details |
| `/update` | Update assistant context |
| `/delete` | Delete the assistant |
| `/test` | Stateless run |
| `/run` | Create a stateful run (interactive: mode, thread, message) |
| `/threads` | List all threads (filtered by graph + assistant) |
| `/delthread` | Delete a thread |
| `/delallthreads` | Delete all threads (filtered by graph + assistant) |

#### /run flow

The `/run` command prompts interactively:

1. **Execution mode**: Stream output, Wait for output, or Background
2. **Create new thread?**: yes/no
3. If yes — optional thread name
4. If no — select from existing threads
5. **Message**: the input to send

Threads are created with `graph_id`, `assistant_id`, and optional `name` in
metadata. Thread listings are filtered by the current scope.

### Exec > Thread (`exec[server]:[graph]:[assistant]:[thread]`)

| Command | Description |
|---------|-------------|
| `/details` | Show thread details |
| `/state` | Show the thread state (messages) |
| `/history` | Show the thread checkpoint history |
| `/delete` | Delete the thread |
| `/update` | Update the thread |
| `/runs` | List runs for this thread |
| `/select` | Select a run |

### Exec > Run (`exec[server]:[graph]:[assistant]:[thread]:[run]`)

| Command | Description |
|---------|-------------|
| `/details` | Get details for this run |
| `/delete` | Delete this run |
| `/cancel` | Cancel this run |

### LLM (`llm`)

| Command | Description |
|---------|-------------|
| `/chat` | Chat with LLM |
| `/code` | LLM with tool use |
| `/models` | List all models with filter |
| `/fetchmodels` | Refresh model list from APIs |
| `/use` | Select a LLM model |

### LLM > Chat (`llm:chat`)

Free text is sent as an LLM prompt.

| Command | Description |
|---------|-------------|
| `/clear` | Clear conversation history |
| `/compact` | Compact conversation history |
| `/debug` | Inspect last LLM request/response |

### LLM > Code (`llm:code:[mode]`)

Free text is sent as a coding task with tool access.

| Command | Description |
|---------|-------------|
| `/plan` | All tool calls require approval |
| `/auto` | Writes require approval |
| `/edit` | No approvals |
| `/clear` | Clear conversation history |
| `/compact` | Compact conversation history |
| `/debug` | Inspect last LLM request/response |

### Server (`server`)

| Command | Description |
|---------|-------------|
| `/list` | List all configured servers |
| `/select` | Select a server |
| `/add` | Add a server |
| `/update` | Update a server |
| `/delete` | Delete a server |

### Server > Selected (`server:[name]`)

| Command | Description |
|---------|-------------|
| `/list` | List all configured servers |
| `/select` | Switch to a different server |
| `/info` | Server version, graphs, status |
| `/reload` | Hot-reload agent repo (langosh server only) |
| `/config` | Show and edit server config (langosh server only) |
| `/apikeys` | Show and edit API keys (langosh server only) |

### Server > Config (`server:[name]:config`)

| Command | Description |
|---------|-------------|
| `/show` | Show server configuration |
| `/reset` | Reset entire server configuration |
| `/configure` | Configure server config step by step |

### Server > API Keys (`server:[name]:apikeys`)

| Command | Description |
|---------|-------------|
| `/list` | List all API keys |
| `/create` | Create an API key |
| `/delete` | Delete an API key |
| `/rotate` | Rotate an API key |

### Settings (`settings`)

| Command | Description |
|---------|-------------|
| `/show` | Show all settings |
| `/configure` | Update settings interactively |

Settings stored in `~/.langosh/settings.json`:

```json
{
  "servers": {
    "local": {"url": "http://localhost:8001", "api_key": null, "langosh_server": true},
    "cloud": {"url": "https://cloud.langgraph.com", "api_key": "lgp-key", "langosh_server": false}
  },
  "active_server": "local",
  "anthropic_api_key": "...",
  "default_provider": "anthropic",
  "max_tokens": 4096
}
```

## Project structure

```
src/langosh/
  main.py                    # CLI entrypoint and REPL
  repl.py                    # Interactive loop, model loading
  input.py                   # Prompt toolkit input with completion + history
  state.py                   # Shared mutable state, Rich console with theme
  settings.py / config.py    # Settings and configuration (multi-server)
  modes/
    __init__.py              # Mode base class, ModeStack, @command decorator
    main.py                  # MainMode (root)
    dev.py                   # DevMode, DevGraphMode
    exec_.py                 # ExecMode, ExecGraphMode, ExecAssistantMode,
                             #   ExecThreadMode, ExecRunMode
    llm.py                   # LlmMode, ChatMode, CodeMode
    server.py                # ServerMode, SelectedServerMode,
                             #   ServerConfigMode, ServerApiKeysMode
    settings_.py             # SettingsMode
  commands/
    typer_cmds.py            # Typer commands (/models, /use, /search, /version)
  llm/
    providers.py             # Multi-provider LLM dispatch
    model_catalog.py         # Dynamic model discovery
    prompts/
      builder.py             # Builder system prompt (tool list from manifest)
    tools/                   # CLI-side tool implementations (for /code mode)
  graphs/
    builder.py               # /create — LLM produces definition.json
    codegen.py               # /compile — definition.json -> __init__.py
    editor.py                # /edit — multi-turn LLM edit loop
    editor_tools.py          # Tools available to the editor LLM
    tool_catalog.py          # Loads tool manifest from langosh-agents
    registry.py              # langgraph.json read/write
  server/
    server_client.py         # HTTP client for langosh-server / langgraph platform
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
