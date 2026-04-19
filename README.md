# Langosh

**A guided CLI to create, test, and run LangGraph agents.**

LangChain and LangGraph are exceptional frameworks. LangChain popularized the
composable agent stack, and LangGraph is the most versatile tool available
today for building stateful, multi-step agents — from simple ReAct loops to
complex custom `StateGraph` pipelines with conditional routing, checkpointing,
and interrupts. The teams have built tools that power agents in production at
serious scale.

That versatility comes with a cost: the learning curve is steep. There's a lot
of surface area to absorb before you can confidently ship something — message
types, state reducers, the Platform API, threads vs. runs vs. assistants,
streaming modes, checkpointers, subgraphs, tool calling patterns. Newcomers
often spend more time reading docs than building.

**Langosh exists to shorten that curve.** It's an opinionated CLI around two
core workflows:

1. **Graph development** — create a new graph with LLM guidance, edit it
   iteratively, compile it, deploy it, test it. One command per step, in the
   order you actually do them.
2. **Graph execution** — pick a server, pick a graph, pick an assistant,
   manage threads, make runs. The concepts are exposed as a mode tree so you
   always know what scope you're in and what commands make sense here.

The LLM side is first-class too: built-in chat with live LangChain docs
lookup (MCP), a code mode with full file/git/exec tooling, subagents for
focused research, and live token streaming across every provider
(Anthropic, OpenAI-compatible, AWS Bedrock, Claude Agent SDK). All with a
single-window input widget that stays responsive while work runs in the
background.

The goal is a CLI where `create → deploy → test → run` feels obvious — so you
can spend your time building agents instead of reading about them.

## Contents

- [Works with LangSmith — and with langosh-server](#works-with-langsmith--and-with-langosh-server)
- [LLM-assisted graph development](#llm-assisted-graph-development)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Navigation](#navigation)
- [Mode tree](#mode-tree)
- [Universal commands](#universal-commands)
- [Commands](#commands)
- [LLM providers](#llm-providers)
- [Built-in tools](#built-in-tools)
- [Project structure](#project-structure)
- [License](#license)

## Works with LangSmith — and with langosh-server

Langosh speaks the **LangGraph Platform API**. That means it works out of the
box with **LangSmith** (LangChain's hosted platform): configure a LangSmith
server URL and API key in `/server /add`, and you can browse graphs, create
assistants, manage threads, make runs, and watch execution from the CLI,
exactly as you would against any LangGraph Platform deployment.

For self-hosting, Langosh ships with a companion project, **[langosh-server](../langosh-server)**,
which re-implements the same LangGraph Platform API — so the CLI can't tell
the difference between a LangSmith-hosted server and a local langosh-server.
What langosh-server adds on top is a small set of **deployment endpoints**
that make the create/test/run loop instant:

- **Hot reload** (`POST /admin/reload`) — point the server at a git-backed
  langgraph-agents repo; push a change, hit reload, and the new graph is live
  without restarting.
- **Admin + config endpoints** — inspect active graphs, manage API keys,
  update server config from the CLI.
- **No build step** — edit your graph JSON or functions, `/deploy` from the
  CLI, and the server picks up the new code on the next run.

The `langosh_server: true` flag on a server entry tells the CLI to expose the
extra admin commands (`/reload`, `/config`, `/apikeys`). For LangSmith or any
plain LangGraph Platform server, set it to `false` and Langosh will show only
the standard Platform commands.

**End-to-end workflow:**

```
$ langosh
> /graphs             # dev mode: local langgraph-agents repo
> /create             # LLM generates definition.json + functions
> /select new-graph   # iterate on the graph (plan/auto/edit)
> "add retry logic"   # LLM edits the graph
> /deploy             # git commit + push + hot reload on the server
> /back /back /exec   # switch to exec mode (on the server)
> /select new-graph   # server now knows about the new graph
> /test               # stateless test run
> /run                # stateful run with a thread
```

Same CLI, same commands — whether you're developing against your own
Langosh Server or hitting a managed LangSmith deployment.

## LLM-assisted graph development

A core design decision in Langosh: **graphs are authored as JSON, not
Python**. When you ask the LLM to create or modify a graph, it edits a
structured `definition.json` file. Langosh's compiler then turns that JSON
into a runnable Python module.

### Why JSON?

LangGraph graphs are normally written as Python — you instantiate a
`StateGraph`, add nodes, wire edges, compile, and export. That works well
for humans, but it's a poor target for an LLM: a tiny formatting mistake
anywhere in the file can break imports, and the LLM has to simultaneously
reason about Python syntax *and* graph semantics.

JSON sidesteps both problems:

- **Structured, validated surface** — the LLM only has to get the *graph
  shape* right. No imports, no syntax, no whitespace. A schema tells it
  which fields exist and what they mean.
- **Reliable partial edits** — the editor can do surgical patches
  (`edit_definition(old_str, new_str)`) without risking syntactic damage
  that would leave an un-loadable Python module on disk.
- **Deterministic output** — compilation from JSON → Python is the same
  every time, so you never get "the LLM's version" of the same graph — you
  get the compiler's.
- **Easy diffing** — a JSON diff of two definitions shows exactly what
  changed in the graph itself, not noise from formatting.

### Graph types

**Simple agents** (`type: "simple"`) — a single ReAct loop. One system
prompt, a list of tool names, and a context schema. The LLM decides which
tools to call at runtime.

```json
{
  "type": "simple",
  "system_prompt": "You are a research assistant.",
  "tools": ["web_search", "fetch_url"],
  "context": {
    "model_name": {"type": "str", "default": "anthropic:claude-sonnet-4-5-20250929"}
  }
}
```

**Custom agents** (`type: "custom"`) — explicit `state`, `nodes`, `edges`.
Use when you need deterministic routing, staged pipelines, or multiple LLM
roles. Node types:

- **`type: "tool"`** — direct tool call as a graph node. Arguments come
  from state or are static. No LLM reasoning.
- **`type: "llm"`** — LLM text generation. Optional `"tools": [...]`
  turns the node into a mini ReAct sub-agent.
- **`type: "function"`** — arbitrary async Python. Escape hatch for logic
  that doesn't fit the other types.

### Tool discovery: curated LangChain tools, build-time only

Langosh never asks the LLM to *guess* which tools exist — it tells it
exactly what's available, sourced from one place: a curated registry of
popular LangChain community tools (Wikipedia, DuckDuckGo, Tavily,
Python REPL, arXiv, PubMed, StackExchange, YouTube, HTTP requests,
shell, file-management, …). All resolution happens at build time inside
the Langosh CLI. The deployed graph has **no runtime tool-discovery code**
— no MCP client, no network call at module import, no surprises at boot.

The agents-repo root carries a tiny `mcp.json` selecting which builtins
to expose:

```json
{
  "builtins": ["wikipedia", "ddg_search", "tavily_search", "python_repl"]
}
```

Omit `builtins` (or the file entirely) to default to the full registry.

Run `/fetchtools` in Langosh to resolve the list and cache the catalog
in `~/.langosh/tools_cache/<hash>.json`. The builder LLM reads from the
cache: tool name, description, parameters, and source tag
(`builtin:wikipedia`). No hallucinated tool names, no invented
parameters.

Every tool is usable the same way in a graph — as a `type: "tool"` node
for deterministic calls, or inside an `llm` node's `"tools": [...]` list
for ReAct-style reasoning. The generated module imports each tool
statically and populates a single `_tools_by_name` dict at module load.

### How the catalog flows

```
mcp.json (builtins)  +  Langosh curated registry
                │
                v  /fetchtools
          builtin registry lookup
                │
                v  catalog
~/.langosh/tools_cache/<hash>.json
                │
                ├─> Builder prompt  (tool signatures + parameters)
                └─> Codegen         (static imports + ctors in the graph module)
```

### The graph compiler

When you run `/compile` (or `/deploy`, which compiles implicitly), Langosh
turns `definition.json` into a runnable Python module at
`graphs/<graph_id>/__init__.py`.

The compiler (`src/langosh/graphs/codegen.py`) does:

1. **Schema validation** — checks the JSON against the type-specific
   schema. Missing fields, invalid node types, unknown state field types,
   or edges pointing to non-existent nodes all surface as clear errors
   before any code is generated.
2. **Tool resolution** — for every tool referenced in `tool` nodes and
   `llm.tools` lists, looks it up in the manifest, gets its module path,
   and emits a correct `from langosh_agents.tools.<module> import <fn>`
   line. Unknown tools raise `ValueError` with the tool name — no silent
   runtime `ImportError` at server boot.
3. **State class generation** — the `state` dict becomes a `TypedDict` (or
   `MessagesState` subclass if `"messages"` is present) with the declared
   field types, including reducers for list/dict fields.
4. **Node emission** — each node type generates its own function:
   - `tool` nodes → a wrapper that reads args from state/context and calls
     the tool.
   - `llm` nodes → a function that formats the prompt template, calls the
     LLM, and (for tool-using llm nodes) emits a nested `create_react_agent`
     with the right tool list.
   - `function` nodes → the provided async code inline.
5. **Graph wiring** — a single `graph = StateGraph(State)` block with
   `add_node` / `add_edge` / `add_conditional_edges` calls matching the
   JSON edges.
6. **Compiled export** — `.compile()` and `graph = ...` so LangGraph's
   runtime can pick it up by pointer from `langgraph.json`.

The generated module is pure, deterministic output — you can read it,
review it in git, and if you want, edit it directly. But typically you
edit the JSON, compile, deploy, and move on.

### Putting it together

```
  /graphs  /create                   # LLM produces definition.json
     ↓
  /select <id>  /edit                # iterative LLM edits on the JSON
     ↓
  /compile                            # JSON → Python module
     ↓
  /deploy                             # git commit + push + server reload
     ↓
  /exec  /select <id>  /test | /run  # run on the server
```

Every step above is one command. The LLM never touches runtime Python;
you never hand-write state reducers; the server always sees a freshly
compiled module that matches the JSON you just approved.

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
| `/initrepo` | Scaffold a minimal langgraph-agents repo in the current directory |
| `/fetchtools` | Refresh the tool catalog from the curated LangChain builtins |
| `/version` | Show the application version |

### Graphs (`graphs`)

Requires the CLI to be started within a langgraph code repository.

| Command | Description |
|---------|-------------|
| `/list` | List all graphs from the current repo |
| `/select` | Select an existing graph to work with |
| `/create` | Create a new graph (LLM-generated) |
| `/fetchtools` | Refresh the tool catalog from the curated LangChain builtins |
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
| `/reload` | Hot-reload agent repo (Langosh Server only) |
| `/config` | Show and edit server config (Langosh Server only) |
| `/apikeys` | Show and edit API keys (Langosh Server only) |

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

## License

MIT
