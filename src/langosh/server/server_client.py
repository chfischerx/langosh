"""Thin async wrapper around `langgraph_sdk` for the Langosh CLI.

The CLI uses this to manage assistants, threads, and stream runs against a
LangGraph Platform / LangSmith deployment (or any langgraph-platform-
compatible API). Connection target is resolved via
`settings.get_server_url()`.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

import httpx
from langgraph_sdk import get_client

from ..settings import get_server_url

# Callback signature: await on_event(event_type, data)
StreamEventCallback = Callable[[str, dict], Awaitable[None]]


# Default per-request timeout. Long enough for normal LLM streams; short
# enough that an unreachable server fails fast instead of hanging the CLI.
_DEFAULT_TIMEOUT = 30.0


def _client(timeout: float = _DEFAULT_TIMEOUT):
    return get_client(url=get_server_url(), timeout=timeout)


async def health_check() -> bool:
    """Return True if the server responds at /ok."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as http:
            r = await http.get(f"{get_server_url()}/ok")
            return r.status_code == 200
    except Exception:
        return False


async def list_assistants(limit: int = 50) -> list[dict]:
    """Return all assistants on the server (up to `limit`)."""
    return list(await _client().assistants.search(limit=limit))


async def ensure_assistant(graph_id: str, *, name: str | None = None) -> dict:
    """Return an existing assistant for this graph_id, or create one.

    When creating, reads default context values from the graph's
    definition.json so the assistant starts with sensible defaults.
    """
    client = _client()
    matches = await client.assistants.search(graph_id=graph_id, limit=10)
    matches = list(matches)
    if matches:
        return matches[0]

    # Read default context from definition.json if available
    context: dict[str, Any] | None = None
    try:
        from ..graphs.registry import graph_dir

        defn_path = graph_dir(graph_id) / "definition.json"
        if defn_path.is_file():
            import json

            defn = json.loads(defn_path.read_text())
            ctx_schema = defn.get("context", {})
            if ctx_schema:
                context = {k: v.get("default") for k, v in ctx_schema.items() if "default" in v}
    except Exception:
        pass  # Non-fatal — create without context

    kwargs: dict[str, Any] = {
        "name": name or graph_id,
        "if_exists": "do_nothing",
    }
    if context:
        kwargs["context"] = context
    return await client.assistants.create(graph_id=graph_id, **kwargs)


async def create_assistant(
    graph_id: str, name: str, *, context: dict | None = None
) -> dict:
    """Create a new custom assistant for a graph with optional context."""
    import re

    client = _client()
    # Derive a unique assistant_id from graph_id + name so multiple
    # assistants can coexist for the same graph.
    slug = re.sub(r"[^\w]+", "_", name.lower()).strip("_")
    assistant_id = f"{graph_id}_{slug}"
    kwargs: dict[str, Any] = {"name": name, "assistant_id": assistant_id}
    if context:
        kwargs["context"] = context
    return await client.assistants.create(graph_id, **kwargs)


async def get_assistant(assistant_id: str) -> dict:
    """GET /assistants/{assistant_id} — full assistant details."""
    return await _client().assistants.get(assistant_id)


async def list_graph_assistants(graph_id: str) -> list[dict]:
    """List all assistants for a specific graph."""
    return list(await _client().assistants.search(graph_id=graph_id, limit=100))


async def update_assistant(
    assistant_id: str,
    *,
    context: dict | None = None,
    name: str | None = None,
    description: str | None = None,
) -> dict:
    """PATCH /assistants/{id} — update context, name, or description."""
    client = _client()
    kwargs: dict[str, Any] = {}
    if context is not None:
        kwargs["context"] = context
    if name is not None:
        kwargs["name"] = name
    if description is not None:
        kwargs["description"] = description
    return await client.assistants.update(assistant_id, **kwargs)


async def delete_assistant(assistant_id: str) -> None:
    """DELETE /assistants/{assistant_id}."""
    await _client().assistants.delete(assistant_id)


async def get_assistant_graph(assistant_id: str) -> dict:
    """Return the JSON node/edge structure of the assistant's graph."""
    return await _client().assistants.get_graph(assistant_id)


async def get_assistant_schemas(assistant_id: str) -> dict:
    """GET /assistants/{assistant_id}/schemas — input/output/context schemas."""
    return await _client().assistants.get_schemas(assistant_id)


async def create_thread(*, metadata: dict | None = None) -> dict:
    """Create a new conversation thread."""
    return await _client().threads.create(metadata=metadata)


async def get_thread(thread_id: str) -> dict:
    """GET /threads/{thread_id} — thread details."""
    return await _client().threads.get(thread_id)


async def search_threads(
    limit: int = 20, *, metadata: dict | None = None
) -> list[dict]:
    """POST /threads/search — list recent threads, optionally filtered by metadata."""
    return list(await _client().threads.search(limit=limit, metadata=metadata))


async def delete_thread(thread_id: str) -> None:
    """Delete a thread and its checkpoints."""
    await _client().threads.delete(thread_id)


async def get_thread_state(thread_id: str) -> dict:
    """GET /threads/{thread_id}/state — current state (messages, etc.)."""
    return await _client().threads.get_state(thread_id)


async def get_thread_history(thread_id: str, limit: int = 10) -> list[dict]:
    """POST /threads/{thread_id}/history — checkpoint history."""
    return list(await _client().threads.get_history(thread_id, limit=limit))


async def stream_run(
    assistant_id: str,
    thread_id: str | None,
    messages: list[dict],
    *,
    context: dict | None = None,
    on_event: StreamEventCallback | None = None,
    stream_mode: str = "messages-tuple",
) -> dict:
    """Stream a run; emit incremental events; return the final text + run_id.

    `stream_mode` is passed through to the server. The rich token /
    tool-call / tool-result parsing only runs when it equals
    `"messages-tuple"` (the default). For any other mode we emit a
    generic `("chunk", {"event": ..., "data": ...})` event per part
    and leave display to the caller.

    `on_event` callbacks:
      - ("run_start",  {"run_id": "..."}):           run accepted by the server
      - ("token",      {"text": "..."}):             streaming assistant text chunk (messages-tuple only)
      - ("tool_call",  {"name": "...", "input": {}}):tool invoked (messages-tuple only)
      - ("tool_result",{"name": "...", "preview": "..."}): tool finished (messages-tuple only)
      - ("chunk",      {"event": "...", "data": ...}): raw server part (non-default modes)
      - ("error",      {"message": "..."}):          server-side error
    Returns {"text": <full assistant text>, "run_id": <str>}.
    """
    client = _client()
    text_chunks: list[str] = []
    run_id = ""
    rich_parse = stream_mode == "messages-tuple"

    stream_kwargs: dict[str, Any] = {
        "input": {"messages": messages},
        "stream_mode": stream_mode,
    }
    if context:
        stream_kwargs["context"] = context

    async for part in client.runs.stream(thread_id, assistant_id, **stream_kwargs):
        event = getattr(part, "event", None)
        data = getattr(part, "data", None)

        if event == "metadata" and isinstance(data, dict):
            run_id = data.get("run_id", "") or run_id
            if on_event:
                await on_event("run_start", {"run_id": run_id})
            continue

        if not rich_parse:
            # Non-default modes get a single passthrough event per part.
            if on_event and event and event != "metadata":
                await on_event("chunk", {"event": event, "data": data})
            if event == "error" and isinstance(data, dict):
                msg = data.get("message") or data.get("error") or "Unknown error"
                raise RuntimeError(f"Server run failed: {msg}")
            continue

        if event in ("messages", "messages/partial") and isinstance(data, (list, tuple)) and data:
            # Data format: ["messages", [chunk_dict, metadata_dict]]
            # or just [chunk_dict, metadata_dict] depending on server version
            payload = data
            if len(payload) >= 2 and isinstance(payload[0], str) and payload[0] == "messages":
                payload = payload[1]  # unwrap the outer ["messages", ...] wrapper
            if not isinstance(payload, (list, tuple)) or not payload:
                continue

            chunk = payload[0] if len(payload) > 0 else {}
            if not isinstance(chunk, dict):
                continue

            # Handle LangChain constructor format: {"lc": 1, "kwargs": {"content": ..., "type": ...}}
            if "kwargs" in chunk:
                kwargs = chunk["kwargs"]
                msg_type = kwargs.get("type", chunk.get("type", ""))
                raw_content = kwargs.get("content", "")
                tool_calls = kwargs.get("tool_calls") or []
                chunk_name = kwargs.get("name", "")
            else:
                msg_type = chunk.get("type", "")
                raw_content = chunk.get("content", "")
                tool_calls = chunk.get("tool_calls") or []
                chunk_name = chunk.get("name", "")

            # Extract text from content — can be a plain string or a list
            # of content blocks (e.g. [{"type": "text", "text": "..."}])
            if msg_type in ("AIMessageChunk", "AIMessage", "ai"):
                text = ""
                if isinstance(raw_content, str):
                    text = raw_content
                elif isinstance(raw_content, list):
                    text = "".join(
                        block.get("text", "")
                        for block in raw_content
                        if isinstance(block, dict) and block.get("type") == "text"
                    )
                if text:
                    text_chunks.append(text)
                    if on_event:
                        await on_event("token", {"text": text})

            for tc in tool_calls:
                if isinstance(tc, dict) and tc.get("name"):
                    if on_event:
                        await on_event("tool_call", {"name": tc["name"], "input": tc.get("args") or {}})

            if msg_type in ("ToolMessage", "tool") and on_event:
                preview = raw_content if isinstance(raw_content, str) else str(raw_content)
                await on_event("tool_result", {"name": chunk_name, "preview": preview[:200]})

        elif event == "error" and isinstance(data, dict):
            msg = data.get("message") or data.get("error") or "Unknown error"
            if on_event:
                await on_event("error", {"message": msg})
            raise RuntimeError(f"Server run failed: {msg}")

    return {"text": "".join(text_chunks), "run_id": run_id}


async def wait_run(
    assistant_id: str,
    thread_id: str | None,
    messages: list[dict],
    *,
    context: dict | None = None,
    stream_mode: str | None = None,
) -> dict:
    """Non-streaming run; block until complete; return final output.

    Works with a thread (conversational) or thread_id=None (stateless).
    `stream_mode`, when set, is passed through to the wait endpoint —
    the server uses it to decide which output format to return
    (`values`, `updates`, `messages-tuple`, …). When unset the server
    defaults (typically `values`).
    Returns {"text": <assistant text>, "output": <raw final payload>}.
    """
    client = _client(timeout=120.0)
    kwargs: dict[str, Any] = {
        "input": {"messages": messages},
    }
    if context:
        kwargs["context"] = context
    if stream_mode:
        kwargs["stream_mode"] = stream_mode

    result = await client.runs.wait(thread_id, assistant_id, **kwargs)

    # Extract text from the final state
    text = ""
    if isinstance(result, dict):
        msgs = result.get("messages", [])
        for msg in reversed(msgs):
            kw = msg.get("kwargs", msg)
            msg_type = kw.get("type", "")
            if msg_type in ("ai", "AIMessage", "AIMessageChunk"):
                content = kw.get("content", "")
                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    text = "".join(
                        b.get("text", "") for b in content
                        if isinstance(b, dict) and b.get("type") == "text"
                    )
                break

    return {"text": text, "output": result}


async def background_run(
    assistant_id: str,
    thread_id: str | None,
    messages: list[dict],
    *,
    context: dict | None = None,
    stream_mode: str | None = None,
) -> dict:
    """Fire-and-forget run. Returns the Run object immediately.

    Pass `thread_id=None` for a stateless run (routes to `POST /runs`
    instead of `POST /threads/{id}/runs`). `stream_mode`, when set,
    is stored on the run so a future rejoin-stream call respects the
    requested format.
    """
    client = _client()
    kwargs: dict[str, Any] = {"input": {"messages": messages}}
    if context:
        kwargs["context"] = context
    if stream_mode:
        kwargs["stream_mode"] = stream_mode
    result = await client.runs.create(thread_id, assistant_id, **kwargs)
    return result


async def list_runs(thread_id: str, limit: int = 10) -> list[dict]:
    """List recent runs for a thread."""
    return list(await _client().runs.list(thread_id, limit=limit))


# ── server info ─────────────────────────────────────────────────────────────


def _base_url() -> str:
    return get_server_url().rstrip("/")


async def server_info() -> dict:
    """GET /info — server version, loaded graphs, etc.

    Standard on LangGraph Platform and LangSmith deployments."""
    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as http:
        r = await http.get(f"{_base_url()}/info")
        r.raise_for_status()
        return r.json()
