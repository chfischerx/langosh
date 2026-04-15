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
    """Return an existing assistant for this graph_id, or create one."""
    client = _client()
    matches = await client.assistants.search(graph_id=graph_id, limit=10)
    matches = list(matches)
    if matches:
        return matches[0]
    return await client.assistants.create(
        graph_id=graph_id,
        name=name or graph_id,
        if_exists="do_nothing",
    )


async def get_assistant_graph(assistant_id: str) -> dict:
    """Return the JSON node/edge structure of the assistant's graph."""
    return await _client().assistants.get_graph(assistant_id)


async def create_thread() -> dict:
    """Create a new conversation thread."""
    return await _client().threads.create()


async def delete_thread(thread_id: str) -> None:
    """Delete a thread and its checkpoints."""
    await _client().threads.delete(thread_id)


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

        elif event == "messages" and isinstance(data, (list, tuple)) and data:
            chunk = data[0] if len(data) > 0 else {}
            if not isinstance(chunk, dict):
                continue
            msg_type = chunk.get("type", "")
            content = chunk.get("content", "")

            if msg_type in ("AIMessageChunk", "AIMessage", "ai") and isinstance(content, str) and content:
                text_chunks.append(content)
                if on_event:
                    await on_event("token", {"text": content})

            tool_calls = chunk.get("tool_calls") or []
            for tc in tool_calls:
                if isinstance(tc, dict) and tc.get("name"):
                    if on_event:
                        await on_event("tool_call", {"name": tc["name"], "input": tc.get("args") or {}})

            if msg_type in ("ToolMessage", "tool") and on_event:
                preview = content if isinstance(content, str) else str(content)
                await on_event("tool_result", {"name": chunk.get("name", ""), "preview": preview[:200]})

        elif event == "error" and isinstance(data, dict):
            msg = data.get("message") or data.get("error") or "Unknown error"
            if on_event:
                await on_event("error", {"message": msg})
            raise RuntimeError(f"Server run failed: {msg}")

    return {"text": "".join(text_chunks), "run_id": run_id}
