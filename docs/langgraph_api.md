# LangGraph API Implementation

Reference for how Langosh's HTTP client
(`src/langosh/server/server_client.py`) maps to the LangGraph Platform
API served by a running `langgraph up` / `langgraph dev` instance
(OpenAPI at `http://127.0.0.1:8123/openapi.json`, title
*"LangSmith Deployment"*).

Sections:

1. [Implemented](#implemented) — client function → endpoint → CLI command.
2. [Deltas](#deltas) — client functions that aren't wired up and server
   endpoints we don't implement at all.
3. [Regenerating this document](#regenerating-this-document).

## Implemented

Each row is a live path from a Langosh CLI command through the client
module down to a LangGraph server endpoint.

| Client function | Endpoint | Used by |
|---|---|---|
| `server_info` | `GET /info` | `/info` (SelectedServerMode) |
| `list_assistants` | `POST /assistants/search` | `/list`, `/select` (ExecMode) |
| `list_graph_assistants` | `POST /assistants/search?graph_id=…` | `/select`, `/search` (ExecGraphMode); `/update` (ExecAssistantMode) |
| `ensure_assistant` | `POST /assistants/search` + fallback `POST /assistants` | `/test`, `/run`, `/show`, `/thread` (ExecGraphMode) |
| `create_assistant` | `POST /assistants` | `/create` (ExecGraphMode) |
| `get_assistant` | `GET /assistants/{id}` | `/show` (ExecAssistantMode) |
| `update_assistant` | `PATCH /assistants/{id}` | `/update` (ExecAssistantMode) |
| `delete_assistant` | `DELETE /assistants/{id}` | `/delete` (ExecAssistantMode) |
| `get_assistant_graph` | `GET /assistants/{id}/graph` | `/show` (ExecGraphMode) |
| `create_thread` | `POST /threads` | `/run` (ExecGraphMode, ExecAssistantMode) via `_run_interactive` |
| `search_threads` | `POST /threads/search` | `/threads`, `/delthread`, `/delallthreads` (\_ThreadCommandsMixin); `/thread`, `/run` (ExecGraphMode, ExecAssistantMode) |
| `get_thread` | `GET /threads/{id}` | `/details` (ExecThreadMode) |
| `delete_thread` | `DELETE /threads/{id}` | `/delthread`, `/delallthreads` (\_ThreadCommandsMixin); `/delete` (ExecThreadMode) |
| `get_thread_state` | `GET /threads/{id}/state` | `/state` (ExecThreadMode) |
| `get_thread_history` | `GET /threads/{id}/history` | `/history` (ExecThreadMode) |
| `list_runs` | `GET /threads/{id}/runs` | `/runs`, `/select` (ExecThreadMode) |
| `stream_run` | `POST /threads/{id}/runs/stream` (with `thread_id`) / `POST /runs/stream` (with `thread_id=None`) | `/test` (stateless, `thread_id=None`); `/run` via `_execute_run` |
| `wait_run` | `POST /threads/{id}/runs/wait` / `POST /runs/wait` | `/test` + `/run` (Wait for output branch) via `_execute_run` |
| `background_run` | `POST /threads/{id}/runs` / `POST /runs` | `/test` + `/run` (Background branch) via `_execute_run` |

**Stateless routing.** All three run functions take
`thread_id: str | None`. The `langgraph-sdk` client dispatches to the
`/runs/*` variant (stateless) when `thread_id is None`, and to
`/threads/{id}/runs/*` otherwise. `/test` always passes
`thread_id=None`, so the whole Stateless-Runs endpoint group
(`/runs`, `/runs/stream`, `/runs/wait`) is already covered.
`POST /runs/batch` is the only one in the group without coverage.

**`stream_mode` parameter.** All three run functions accept an
optional `stream_mode` (default `"messages-tuple"` for `stream_run`,
`None` for wait/background — server chooses). The CLI asks for it in
`/test` and `/run` right after the execution-mode picker. Supported
values: `messages-tuple`, `values`, `updates`, `messages`, `events`,
`custom`, `debug`.

Helpers `_execute_run`, `_stateless_test`, and `_run_interactive` in
`src/langosh/modes/exec_.py` are the plumbing that connects the
`/test` and `/run` commands to the three run-creation variants
(`stream_run`, `wait_run`, `background_run`), threading `stream_mode`
through each.

## Deltas

### Defined in the client but not wired up

| Client function | Server endpoint |
|---|---|
| `health_check` | `GET /ok` |
| `get_assistant_schemas` | `GET /assistants/{assistant_id}/schemas` |

Suggested actions:

- `health_check` — surface as a startup-banner indicator (green dot
  when the active server responds at `/ok`, red otherwise) or drop it.
- `get_assistant_schemas` — expose as an assistant-mode `/schemas`
  command (shows input / output / context schemas).

### Not implemented in the client

Grouped by OpenAPI tag.

#### Assistants — 5 of 12 missing

| Method | Path | Notes |
|---|---|---|
| POST | `/assistants/count` | Count-only helper for large lists. |
| POST | `/assistants/{assistant_id}/latest` | Set active version. |
| POST | `/assistants/{assistant_id}/versions` | List versions. |
| GET  | `/assistants/{assistant_id}/subgraphs` | Enumerate subgraphs. |
| GET  | `/assistants/{assistant_id}/subgraphs/{namespace}` | Inspect a subgraph. |

#### Threads — 9 of 14 missing

| Method | Path | Notes |
|---|---|---|
| POST | `/threads/count` | Count-only helper. |
| POST | `/threads/prune` | Bulk delete by filter. |
| PATCH | `/threads/{thread_id}` | Update thread metadata. |
| POST | `/threads/{thread_id}/copy` | Fork a thread. |
| POST | `/threads/{thread_id}/history` | Filtered / paginated history (we only use the GET form). |
| POST | `/threads/{thread_id}/state` | Update state. |
| POST | `/threads/{thread_id}/state/checkpoint` | Write at a specific checkpoint. |
| GET  | `/threads/{thread_id}/state/{checkpoint_id}` | Read state at a specific checkpoint. |
| GET  | `/threads/{thread_id}/stream` | Join the active run stream. |

#### Thread runs — 6 of 10 missing

| Method | Path | Notes |
|---|---|---|
| POST | `/runs/cancel` | Batch cancel. |
| GET  | `/threads/{thread_id}/runs/{run_id}` | Fetch a specific run. |
| DELETE | `/threads/{thread_id}/runs/{run_id}` | Delete a run. |
| POST | `/threads/{thread_id}/runs/{run_id}/cancel` | Cancel one run. |
| GET  | `/threads/{thread_id}/runs/{run_id}/join` | Block-wait for completion. |
| GET  | `/threads/{thread_id}/runs/{run_id}/stream` | Rejoin the run stream. |

#### Stateless runs — 1 of 4 missing

| Method | Path | Notes |
|---|---|---|
| POST | `/runs/batch` | No client coverage. |

The other three stateless endpoints (`POST /runs`, `POST /runs/stream`,
`POST /runs/wait`) are reached via the existing
`background_run` / `stream_run` / `wait_run` functions when
`thread_id=None` — `langgraph-sdk` picks the `/runs/*` form over the
`/threads/{id}/runs/*` form based on that argument. `/test` uses this
path in both ExecGraphMode and ExecAssistantMode.

#### Crons — whole group missing (6 endpoints)

| Method | Path |
|---|---|
| POST | `/runs/crons` |
| POST | `/runs/crons/count` |
| POST | `/runs/crons/search` |
| PATCH | `/runs/crons/{cron_id}` |
| DELETE | `/runs/crons/{cron_id}` |
| POST | `/threads/{thread_id}/runs/crons` |

#### Store — whole group missing (5 endpoints)

| Method | Path |
|---|---|
| PUT | `/store/items` |
| DELETE | `/store/items` |
| GET | `/store/items` |
| POST | `/store/items/search` |
| POST | `/store/namespaces` |

#### MCP (server-side gateway) — whole group missing (3 endpoints)

| Method | Path |
|---|---|
| POST | `/mcp/` |
| GET  | `/mcp/` |
| DELETE | `/mcp/` |

Orthogonal to the CLI-side curated tool catalog — this is the server's
own MCP gateway.

#### A2A — missing

| Method | Path |
|---|---|
| POST | `/a2a/{assistant_id}` |

#### System — 1 missing

| Method | Path | Notes |
|---|---|---|
| GET | `/metrics` | Prometheus metrics. |

### Triage

- **Low-effort, high-value additions** — cancel a run, rejoin an
  existing run stream, update thread metadata, checkpoint-specific
  state read, assistant version list/set-latest. These map directly to
  existing exec-mode UX gaps (can't cancel a runaway run, can't
  reconnect after a disconnect, can't pin a version).
- **Probably out of scope for this CLI** — Store, Crons, MCP server
  endpoints, A2A, metrics. They serve production operators, not the
  create → iterate → test loop Langosh optimizes for.
- **Housekeeping** — either wire up `health_check` and
  `get_assistant_schemas` or delete them so the client module doesn't
  carry dead code.

## Regenerating this document

```bash
# Dump the current spec into docs/:
curl -sS http://127.0.0.1:8123/openapi.json > docs/openapi.json

# Then diff against server_client.py's coverage — the Python script
# used to produce this report is in git history under the commit that
# introduced it (grep the tree for `openapi.json` + Python one-liners).
```
