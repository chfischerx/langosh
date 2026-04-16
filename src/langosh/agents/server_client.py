"""Thin async wrapper around `langgraph_sdk` for the langosh CLI.

The CLI uses this to manage assistants, threads, and stream runs against a
self-hosted langosh-server (or any langgraph-platform-compatible API).

Connection target is resolved via `settings.get_server_url()`.
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
        from .registry import graph_dir

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


async def create_thread() -> dict:
    """Create a new conversation thread."""
    return await _client().threads.create()


async def get_thread(thread_id: str) -> dict:
    """GET /threads/{thread_id} — thread details."""
    return await _client().threads.get(thread_id)


async def search_threads(limit: int = 20) -> list[dict]:
    """POST /threads/search — list recent threads."""
    return list(await _client().threads.search(limit=limit))


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
) -> dict:
    """Stream a run; emit incremental events; return the final text + run_id.

    `on_event` callbacks:
      - ("run_start",  {"run_id": "..."}):           run accepted by the server
      - ("token",      {"text": "..."}):             streaming assistant text chunk
      - ("tool_call",  {"name": "...", "input": {}}):tool invoked by the model
      - ("tool_result",{"name": "...", "preview": "..."}): tool finished
      - ("error",      {"message": "..."}):          server-side error
    Returns {"text": <full assistant text>, "run_id": <str>}.
    """
    client = _client()
    text_chunks: list[str] = []
    run_id = ""

    stream_kwargs: dict[str, Any] = {
        "input": {"messages": messages},
        "stream_mode": "messages-tuple",
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

        elif event in ("messages", "messages/partial") and isinstance(data, (list, tuple)) and data:
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


# ── admin / server info endpoints ────────────────────────────────────────────


def _base_url() -> str:
    return get_server_url().rstrip("/")


async def server_info() -> dict:
    """GET /info — server version, loaded graphs, etc."""
    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as http:
        r = await http.get(f"{_base_url()}/info")
        r.raise_for_status()
        return r.json()


async def reload_agents() -> dict:
    """POST /admin/reload — hot-reload graphs without restarting the server."""
    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as http:
        r = await http.post(f"{_base_url()}/admin/reload")
        r.raise_for_status()
        return r.json()


async def list_api_keys() -> list[dict]:
    """GET /admin/keys — list all API keys."""
    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as http:
        r = await http.get(f"{_base_url()}/admin/keys")
        r.raise_for_status()
        return r.json()


async def create_api_key(name: str) -> dict:
    """POST /admin/keys — create a new API key."""
    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as http:
        r = await http.post(f"{_base_url()}/admin/keys", json={"name": name})
        r.raise_for_status()
        return r.json()


async def delete_api_key(name: str) -> None:
    """DELETE /admin/keys/{name} — delete an API key."""
    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as http:
        r = await http.delete(f"{_base_url()}/admin/keys/{name}")
        r.raise_for_status()


async def rotate_api_key(name: str) -> dict:
    """POST /admin/keys/{name}/rotate — rotate an API key."""
    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as http:
        r = await http.post(f"{_base_url()}/admin/keys/{name}/rotate")
        r.raise_for_status()
        return r.json()


# ── config endpoints ────────────────────────────────────────────────────────


async def get_config_schema() -> list[dict]:
    """GET /admin/config/schema — all supported config params."""
    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as http:
        r = await http.get(f"{_base_url()}/admin/config/schema")
        r.raise_for_status()
        return r.json()


async def list_config(category: str | None = None) -> list[dict]:
    """GET /admin/config or /admin/config/{category}."""
    path = f"/admin/config/{category}" if category else "/admin/config"
    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as http:
        r = await http.get(f"{_base_url()}{path}")
        r.raise_for_status()
        return r.json()


async def set_config(category: str, key: str, value: str) -> dict:
    """PUT /admin/config/{category} — set a config value."""
    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as http:
        r = await http.put(
            f"{_base_url()}/admin/config/{category}",
            json={"key": key, "value": value},
        )
        r.raise_for_status()
        return r.json()


async def delete_config(category: str, key: str) -> dict:
    """DELETE /admin/config/{category}/{key} — remove a config value."""
    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as http:
        r = await http.delete(f"{_base_url()}/admin/config/{category}/{key}")
        r.raise_for_status()
        return r.json()


async def reset_config() -> dict:
    """POST /admin/config/reset — delete all config keys."""
    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as http:
        r = await http.post(f"{_base_url()}/admin/config/reset")
        r.raise_for_status()
        return r.json()
