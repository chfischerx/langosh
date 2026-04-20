# Langosh

[![PyPI version](https://img.shields.io/pypi/v/langosh.svg?color=7ee787&label=pypi)](https://pypi.org/project/langosh/)
[![Python versions](https://img.shields.io/pypi/pyversions/langosh.svg?color=7ee787)](https://pypi.org/project/langosh/)
[![License](https://img.shields.io/github/license/chfischerx/langosh.svg?color=7ee787)](https://github.com/chfischerx/langosh/blob/main/LICENSE)
[![CI](https://github.com/chfischerx/langosh/actions/workflows/ci.yml/badge.svg)](https://github.com/chfischerx/langosh/actions/workflows/ci.yml)
[![Publish](https://github.com/chfischerx/langosh/actions/workflows/publish.yml/badge.svg)](https://github.com/chfischerx/langosh/actions/workflows/publish.yml)
[![Issues](https://img.shields.io/github/issues/chfischerx/langosh.svg?color=d2a8ff)](https://github.com/chfischerx/langosh/issues)
[![GitHub stars](https://img.shields.io/github/stars/chfischerx/langosh.svg?color=d2a8ff&label=★)](https://github.com/chfischerx/langosh/stargazers)

A CLI for building and running LangGraph agents. You scaffold a repo, ask
an LLM to write you a graph, test it locally with `langgraph dev`, and
point the same CLI at a LangSmith / LangGraph Platform deployment to
drive runs against a real server.

The gist: LangGraph is powerful but there's a lot to learn — message
types, reducers, checkpointers, threads vs. runs vs. assistants,
streaming modes, tool bindings. Langosh doesn't hide any of that, but it
tries to put the steps in the order you actually do them, and lets the
LLM handle the `StateGraph(...).add_node(...)` boilerplate so you can
spend more time on graph logic than on imports.

A few things worth calling out:

- **Graphs are authored as JSON, not Python.** The LLM edits a
  `definition.json`; a compiler emits the Python module. Easier for the
  LLM to reason about, easier for you to diff.
- **Tool resolution happens at build time.** The builder sees a live
  catalog pulled from `langchain_community.tools` +
  `langchain_experimental.tools`; the generated graph just imports what
  it needs. No runtime discovery, no surprises at server boot.
- **Any LangGraph-Platform-compatible server works.** Local
  `langgraph dev` / `langgraph up` for iteration, LangSmith-hosted for
  production.
- **There's a built-in `/chat` and `/code` mode** that uses whichever
  LLM provider you've configured (Anthropic, OpenAI-style, Bedrock, or
  the Claude Agent SDK) — handy for quick doc lookups and code edits
  without leaving the terminal.

## Contents

- [Works with LangGraph Platform / LangSmith](#works-with-langgraph-platform--langsmith)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [LLM-assisted graph development](#llm-assisted-graph-development)
- [Testing an agents repo locally](#testing-an-agents-repo-locally)
- [Navigation](#navigation)
- [Mode tree](#mode-tree)
- [Universal commands](#universal-commands)
- [Commands](#commands)
- [LLM providers](#llm-providers)
- [Built-in tools](#built-in-tools)
- [Project structure](#project-structure)
- [License](#license)

## Works with LangGraph Platform / LangSmith

Langosh is primarily a **graph development tool** — scaffold a repo,
author a `definition.json` with an LLM, compile to Python, iterate.

For **testing** the graphs you've just built, Langosh ships a small
built-in LangGraph client (wrapping the
[`langgraph-sdk`](https://pypi.org/project/langgraph-sdk/)) that talks
to any LangGraph-Platform-compatible server: a local `langgraph dev` /
`langgraph up` instance, or a LangSmith-hosted deployment. Point at
one via `/server /add`; everything downstream (`/exec`, `/test`,
`/run`) hits that server.

**The client is deliberately scoped.** Only the endpoints that are
useful during graph development are implemented — enough to:

- invoke a graph with different **assistant** contexts (models,
  system prompts, per-run parameters);
- **monitor runs** — stream tokens, watch tool calls, wait for
  completion, inspect thread state and history;
- **collect diagnostic information** from completed runs and feed it
  back into the LLM editor so the builder can reason about what
  actually happened.

Operational surfaces (Store, Crons, MCP gateway, batch cancels,
A2A, Prometheus metrics) are intentionally out of scope. See the
[LangGraph API coverage document](https://github.com/chfischerx/langosh/blob/main/docs/langgraph_api.md)
for the full endpoint-to-command map and the explicit list of
omissions.

## Requirements

- Python 3.11+
- A running LangGraph-compatible server instance (optional — only needed for exec mode)
- An agents repo in the current working directory (create one with `/initrepo`)

## Installation

From PyPI:

```sh
pip install langosh
```

Or with `uv`:

```sh
uv tool install langosh
```

Verify:

```sh
langosh version
```

### From source (for contributing)

```sh
git clone https://github.com/chfischerx/langosh.git
cd langosh
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

### Tool discovery: LangChain community, build-time only

Langosh never asks the LLM to *guess* which tools exist — it tells it
exactly what's available. At `/fetchtools` time, the CLI introspects
`langchain_community.tools` and `langchain_experimental.tools` for every
`BaseTool` subclass whose constructor matches a supported pattern
(zero-arg or `api_wrapper=XxxAPIWrapper()`). A small override table in
`tool_discovery.py` adds the few tools whose ctor needs special args
(e.g. `RequestsGetTool` with `allow_dangerous_requests=True`).

All resolution happens at build time inside the Langosh CLI. The
deployed graph has **no runtime tool-discovery code** — no MCP client,
no network call at module import, no surprises at boot.

Run `/fetchtools` in Langosh to refresh the catalog at
`~/.langosh/tools_cache/<hash>.json`. The builder LLM reads from the
cache: tool name, description, parameters, and source tag
(`community:ddg_search.tool`, `experimental:python.tool`, …). No
hallucinated tool names, no invented parameters.

Every tool is usable the same way in a graph — as a `type: "tool"` node
for deterministic calls, or inside an `llm` node's `"tools": [...]` list
for ReAct-style reasoning. The generated module imports each tool
statically and populates a single `_tools_by_name` dict at module load.

### How the catalog flows

```
langchain_community.tools + langchain_experimental.tools  (+ overrides)
                │
                v  /fetchtools
          discovered catalog
                │
                v
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
   `llm.tools` lists, looks it up in the cached catalog and emits the
   matching `from langchain_community.tools... import ...` line plus a
   static constructor expression. Unknown tools raise `ValueError` with
   the tool name — no silent runtime `ImportError` at server boot.
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

## Testing an agents repo locally

`langgraph-cli` is wired into the scaffold (`[dependency-groups] dev`).
After `/initrepo` + `uv sync`, use one of the two commands LangGraph
ships for local testing — both read the repo's `langgraph.json` and
load any env vars declared via its `env` field. See the [LangSmith
local dev docs](https://docs.langchain.com/langsmith/local-dev-testing)
for the full reference.

### `langgraph dev` — fast, in-process

```bash
uv run langgraph dev
```

- Default port: `2024`.
- **Hot reload is on by default** — edit `definition.json`, run
  `/compile` in Langosh (or save the generated `__init__.py`), and the
  dev server picks up the change.
- No Docker. State persists in local pickle files — good enough for
  iterating on graph logic.
- Open the Studio UI at
  `https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024`
  for a visual graph runner.

Point Langosh at it once via `/server /add` (URL `http://localhost:2024`)
and `/select` it — now `/exec` in Langosh hits the dev server for
`/test`, `/run`, threads, and assistants.

### `langgraph up --watch` — production-like, Dockerized

```bash
uv run langgraph up --watch
```

- Default port: `8123`.
- Runs the **full Docker stack** — PostgreSQL + Redis + the server —
  so threads, assistants, and long-running runs persist the same way
  they will in production.
- `--watch` enables hot reload (opt-in here, default-on in `dev`).
- Requires Docker. Slower to boot than `dev`; use this right before
  deploying to catch any Postgres-/Redis-specific issues.

`uv run langgraph up --recreate` does a full rebuild — handy after
bumping dependencies in `pyproject.toml`.

### Env vars

Both commands load `.env` (the path is declared in `langgraph.json`'s
`env` field — the scaffold sets it to `./.env`). `/initrepo` pre-fills
`LANGSMITH_PROJECT` and an empty `LANGSMITH_API_KEY`; add your LLM /
tool keys there before launching.

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
│   └── [server_name]        Selected server (info, CRUD)
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
| `/fetchtools` | Refresh the tool catalog by introspecting LangChain community + experimental packages |
| `/version` | Show the application version |

### Graphs (`graphs`)

Requires the CLI to be started within a langgraph code repository.

| Command | Description |
|---------|-------------|
| `/list` | List all graphs from the current repo |
| `/select` | Select an existing graph to work with |
| `/create` | Create a new graph (LLM-generated) |
| `/fetchtools` | Refresh the tool catalog by introspecting LangChain community + experimental packages |
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

### Settings (`settings`)

| Command | Description |
|---------|-------------|
| `/show` | Show all settings |
| `/configure` | Update settings interactively |

Settings stored in `~/.langosh/settings.json`:

```json
{
  "servers": {
    "dev": {"url": "http://localhost:2024"},
    "up":  {"url": "http://localhost:8123"}
  },
  "active_server": "dev",
  "anthropic_api_key": "...",
  "default_provider": "anthropic",
  "max_tokens": 4096
}
```

Server entries carry just a URL — local `langgraph dev` / `langgraph up`
don't need auth, so the CLI doesn't store or send a server-level API key.
(LLM-provider keys — `anthropic_api_key`, `openai_api_key` — are still
stored and used for the CLI's own `/chat` and `/code` modes.)

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
    tool_catalog.py          # loads the cached tool catalog
    tool_discovery.py        # introspects langchain_community.tools
    tool_fetcher.py          # /fetchtools — discovery + cache
    registry.py              # langgraph.json read/write

  server/
    server_client.py         # HTTP client for LangGraph Platform / compatible servers
```

## License

MIT
