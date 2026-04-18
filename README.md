# langosh

A CLI to build, test, and deploy LangGraph agents — with live streaming,
LangChain docs lookup, and subagent delegation baked in.

## Requirements

- Python 3.11+
- A running [langosh-server](../langosh-server) instance (optional — only needed for exec mode)
- The [langosh-agents](../langosh-agents) repo (sibling directory, optional — only needed for dev mode)

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

### Input controls

- **Shift+Tab** — cycle the current sub-mode (`plan` → `auto` → `edit`) where applicable
- **Ctrl+C** (twice within 1 second) — exit
- **Up/Down** — history / completion-menu navigation
- **Tab** — complete commands
- **Escape** — dismiss completion menu

## Mode tree

```
main
├── graphs                   Local graph development (requires langgraph repo)
│   └── [graph_id]:[mode]    LLM-driven editing (plan/auto/edit)
├── exec[server]             Execute graphs on a server
│   └── [graph_id]           Graph-scoped commands
│       └── [assistant]      Assistant-scoped commands
│           └── [thread]     Thread inspection
│               └── [run]    Run inspection
├── chat                     Direct LLM conversation (LangChain docs Q&A)
├── code:[mode]              LLM with tool use (plan/auto/edit)
├── server                   Server management
│   └── [server_name]        Selected server
│       ├── config           Server configuration
│       └── apikeys          API key management
└── settings                 CLI settings
```

## Universal commands

Available in every mode:

| Command | Description |
|---------|-------------|
| `/model` | Select an LLM model |
| `/models` | List all models with optional filter |
| `/fetchmodels` | Refresh model list from APIs |
| `/help` | Show available commands |
| `/back` | Go back to parent mode |
| `/home` | Return to main mode |
| `/cls` | Clear screen |
| `/exit` | Quit |

## Commands

### Main (`main`)

| Command | Description |
|---------|-------------|
| `/graphs` | Local graph development |
| `/exec` | Execute graphs and assistants on a server |
| `/chat` | LLM chat (LangChain docs-backed) |
| `/code` | LLM with tool use |
| `/server` | Server management |
| `/settings` | CLI settings |
| `/version` | Show the application version |

### Graphs (`graphs`)

Requires the CLI to be started within a langgraph code repository.

| Command | Description |
|---------|-------------|
| `/list` | List all graphs from the current repo |
| `/select` | Select an existing graph to work with |
| `/create` | Create a new graph (LLM-generated) |
| `/deploy` | Commit, push, and reload agents on the server |
| `/status` | Show git status |
| `/commit` | Commit all changes |

### Graphs > Graph (`graphs:[graph_id]:[mode]`)

LLM-driven editing. Free text is sent as an edit instruction.

| Command | Description |
|---------|-------------|
| `/plan` | Read-only: reads auto, writes denied |
| `/auto` | Reads auto, writes require approval |
| `/edit` | Auto-approve everything |
| `/compile` | Compile the selected graph (definition.json → Python) |
| `/delete` | Delete the selected graph |
| `/preview` | Visualize the graph as ASCII (via grandalf) |
| `/test` | Stateless test run against the server |
| `/deploy` | Commit, push, and reload agents on the server |
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
| `/show` | Display the graph (ASCII from server) |
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
| `/run` | Create a stateful run |
| `/threads` | List all threads (filtered by graph + assistant) |
| `/delthread` | Delete a thread |
| `/delallthreads` | Delete all threads (filtered by graph + assistant) |

#### /run and /test flow

Both commands prompt interactively:

1. **Execution mode**: Stream output, Wait for output, or Background
2. **Create new thread?** (run only): yes/no
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

### Chat (`chat`)

Free text is sent as an LLM prompt. The chat is framed as a LangChain /
LangGraph / LangSmith expert and has access to the live docs via MCP.

| Command | Description |
|---------|-------------|
| `/clear` | Clear conversation history |
| `/compact` | Compact conversation history |
| `/debug` | Inspect last LLM request/response |

### Code (`code:[mode]`)

Free text is sent as a coding task with full tool access (read/write/exec
+ docs + subagents).

| Command | Description |
|---------|-------------|
| `/plan` | Read-only: reads auto, writes denied |
| `/auto` | Reads auto, writes require approval |
| `/edit` | Auto-approve everything |
| `/clear` | Clear conversation history |
| `/compact` | Compact conversation history |
| `/debug` | Inspect last LLM request/response |

The current sub-mode is shown below the input line and can be cycled with
**Shift+Tab**:

```
⏸ plan mode on (shift+tab to cycle)   [yellow]
▶▶ auto mode on (shift+tab to cycle)  [cyan]
▶▶ edit mode on (shift+tab to cycle)  [magenta]
```

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
| `/add` / `/update` / `/delete` | Server CRUD |
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

## LLM providers

All four providers stream tokens and emit `tool_call` / `tool_result`
events — the UI looks the same regardless of provider:

| Provider | Streaming | Tool use | Notes |
|---|---|---|---|
| `claude_sdk` | ✅ tokens + thinking | ✅ via in-process MCP | Uses your Claude subscription; subprocess stderr captured as status lines |
| `anthropic` | ✅ tokens | ✅ native | Prompt caching (ephemeral) |
| `openai` / `deepseek` / `xai` | ✅ tokens | ✅ function calling | Shared OpenAI-compatible client |
| `bedrock_converse` | ✅ tokens | ✅ native | Prompt caching via cachePoint |

The spinner above the input line updates live with character count, and
tool calls appear inline as they happen:

```
⠋ Calling Claude Opus 4.7 (2534 chars)
  ↳ docs_search(StateGraph conditional edges)
  ↳ docs_search done
  ↳ docs_read(cat langgraph/concepts/stategraph.mdx)
  ↳ docs_read done
```

## Built-in tools

Chat and code modes have access to:

### Documentation tools (chat + code + graph editor)
- `docs_search(query)` — semantic search over LangChain/LangGraph/LangSmith docs (via the [LangChain docs MCP server](https://docs.langchain.com/mcp))
- `docs_read(command)` — shell-like read of the docs filesystem (cat, ls, tree, grep, rg)

### File tools (code)
- `read_file`, `write_file`, `edit_file`
- `list_directory`, `glob_files`, `grep_files`

### Git tools (code)
- `git_status`, `git_diff`, `git_log`, `git_show`, `git_blame`

### Python exec (code)
- `execute_python` — sandboxed subprocess execution

### Subagents (chat + code + graph editor)
- `spawn_subagent(role, task)` — delegate focused work to a fresh agent with a restricted toolset

| Role | Tools |
|---|---|
| `researcher` | `docs_search`, `docs_read` |
| `explorer` | all read tools (file + git + docs) |
| `coder` | reads + `edit_file` + `write_file` |

Subagents run recursively through our provider layer, so their nested
tool calls show up in the main stream with an indented `·` prefix. Max
depth is 2. Useful for keeping the main conversation context lean when
a task requires deep research or focused implementation.

### Approval model (code mode)

Reads are always auto-approved. Writes depend on sub-mode:

| Mode | Reads | Writes |
|---|---|---|
| `plan` | auto | **denied** |
| `auto` | auto | approval prompt |
| `edit` | auto | auto |

## Project structure

```
src/langosh/
  main.py                    # CLI entrypoint
  repl.py                    # REPL loop, model loading
  input.py                   # Prompt toolkit widget (completion, mode bar, spinner, ctrl-c guard)
  worker.py                  # Background worker with shared lock + spinner coordination
  state.py                   # Shared mutable state, Rich console
  settings.py / config.py    # Multi-server settings

  modes/
    __init__.py              # Mode base class, ModeStack, @command decorator
    main.py                  # MainMode (root)
    dev.py                   # DevMode, DevGraphMode (the "graphs" mode)
    exec_.py                 # ExecMode, ExecGraphMode, ExecAssistantMode,
                             #   ExecThreadMode, ExecRunMode
    llm.py                   # ChatMode, CodeMode
    server.py                # ServerMode, SelectedServerMode,
                             #   ServerConfigMode, ServerApiKeysMode
    settings_.py             # SettingsMode

  commands/
    typer_cmds.py            # Typer commands (/models, /model, /search, /ask, /version)

  llm/
    providers.py             # Multi-provider dispatch (streaming)
    claude_sdk.py            # Claude Agent SDK provider
    anthropic.py             # Anthropic API (streaming)
    openai_compat.py         # OpenAI / DeepSeek / xAI (streaming)
    bedrock.py               # AWS Bedrock Converse (streaming)
    model_catalog.py         # Model discovery
    prompts/
      chat.py                # Chat system prompt (LangChain expert)
      code.py                # Code system prompt (LangGraph repo expert)
      builder.py             # Graph builder prompt
    tools/
      file_tools.py
      git_tools.py
      python_exec.py
      docs_tools.py          # LangChain docs MCP wrapper
      subagent_tools.py      # spawn_subagent tool

  graphs/
    builder.py               # /create — LLM produces definition.json
    codegen.py               # /compile — definition.json -> __init__.py
    editor.py                # multi-turn LLM edit loop
    editor_tools.py          # tools for the editor LLM
    tool_catalog.py          # loads tool manifest from langosh-agents
    registry.py              # langgraph.json read/write

  server/
    server_client.py         # HTTP client for langosh-server / LangGraph Platform
```

## Agent tools and codegen

The langosh CLI creates and compiles LangGraph agents. Agent tool metadata
comes from the sibling `langosh-agents` repo's `tools/manifest.json`, which
is generated from the actual tool source files
(see [langosh-agents README](../langosh-agents/README.md)).

### How the tool catalog flows

```
langosh-agents/tools/*.py        (async functions with type hints + docstrings)
        |
        v  scripts/build_manifest.py
langosh-agents/tools/manifest.json  (name, module, params, description)
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
