"""Claude Agent SDK provider.

Chat mode: allowed_tools=[], max_turns=1 (plain chat, no tools)
Tool mode: custom tools are exposed to the SDK via an in-process MCP
server. Our tool_dispatcher runs the actual tool (including any approval
widget); the SDK just routes calls to it.

No API key needed — uses the user's Claude subscription.
"""

import logging
import os

from .debug import capture_request, capture_response
from .types import LLMResult, ToolDispatcher, ToolEventCallback

logger = logging.getLogger(__name__)

try:
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        ResultMessage,
        StreamEvent,
        TextBlock,
        ToolResultBlock,
        ToolUseBlock,
        UserMessage,
        create_sdk_mcp_server,
        query,
        tool,
    )
except ImportError:
    query = None  # type: ignore[assignment]

# SDK's own built-in tools — used only when no custom tools are supplied.
_CODE_TOOLS = ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]

# Map our sub-modes to SDK permission modes (only applies to SDK built-in tools).
_PERMISSION_MAP = {
    "plan": "plan",
    "auto": "acceptEdits",
    "edit": "bypassPermissions",
}

_MCP_SERVER_NAME = "langosh"


def _require_sdk() -> None:
    if query is None:
        raise ImportError(
            "The 'claude-agent-sdk' package is required for the Claude SDK provider. "
            'Install it with: pip install "langosh[claude-sdk]"'
        )


def _messages_to_prompt(messages: list[dict]) -> str:
    """Convert a message list to a single prompt string for the SDK."""
    if len(messages) == 1:
        content = messages[0].get("content", "")
        return content if isinstance(content, str) else ""

    parts = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if not isinstance(content, str):
            content = "(non-text content)"
        if role == "user":
            parts.append(f"User: {content}")
        elif role == "assistant":
            parts.append(f"Assistant: {content}")
    parts.append("\nPlease respond to the latest user message above.")
    return "\n\n".join(parts)


async def _call_sdk(
    prompt: str,
    model: str | None,
    system_prompt: str | None,
    allowed_tools: list[str] | None = None,
    mcp_servers: dict | None = None,
    max_turns: int = 1,
    permission_mode: str | None = None,
    on_event: ToolEventCallback | None = None,
    emit_tool_events: bool = True,
) -> LLMResult:
    """Call the Claude Agent SDK and stream intermediate updates.

    on_event receives:
      ("token", {"text": chunk})            — streaming text deltas
      ("tool_call", {"name", "input"})      — LLM decides to call a tool
      ("tool_result", {"name", "preview"})  — tool returned

    emit_tool_events=False is used when a custom MCP wrapper already emits
    tool_call/tool_result events (avoids duplicates in the custom-tools flow).
    """
    _require_sdk()

    # Capture CLI subprocess stderr and route it through on_event as a
    # "status" event. The SDK sends text in chunks, so we buffer until
    # we see a newline and flush complete lines.
    import re
    _ansi_re = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
    _buf = {"s": ""}

    def _stderr_cb(text: str) -> None:
        if on_event is None:
            return
        _buf["s"] += text
        while "\n" in _buf["s"]:
            line, _buf["s"] = _buf["s"].split("\n", 1)
            clean = _ansi_re.sub("", line).strip()
            if not clean:
                continue
            # Schedule the async callback from the SDK's thread.
            import asyncio as _aio
            try:
                loop = _aio.get_event_loop()
                loop.create_task(on_event("status", {"text": clean}))
            except RuntimeError:
                # No running loop; ignore
                pass

    kwargs: dict = {
        "model": model,
        "max_turns": max_turns,
        "cwd": os.getcwd(),
        # Stream token-level deltas so long responses don't look frozen.
        "include_partial_messages": True,
        # Intercept CLI stderr so it shows as a dim status line instead of
        # raw overwriting our spinner.
        "stderr": _stderr_cb,
    }
    if system_prompt:
        kwargs["system_prompt"] = system_prompt
    if allowed_tools is not None:
        kwargs["allowed_tools"] = allowed_tools
    if mcp_servers:
        kwargs["mcp_servers"] = mcp_servers
    if permission_mode:
        kwargs["permission_mode"] = permission_mode

    options = ClaudeAgentOptions(**kwargs)

    capture_request({
        "prompt": prompt,
        "model": model,
        "system_prompt": system_prompt,
        "allowed_tools": allowed_tools,
        "mcp_servers": list(mcp_servers.keys()) if mcp_servers else [],
        "max_turns": max_turns,
        "permission_mode": permission_mode,
    })

    text = ""
    result_info: dict = {}
    # Track tool_use ids -> names so we can emit tool_result events later.
    tool_names_by_id: dict[str, str] = {}

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, StreamEvent) and on_event is not None:
            # Token-level streaming: emit incremental text deltas.
            ev = message.event or {}
            if ev.get("type") == "content_block_delta":
                delta = ev.get("delta", {}) or {}
                if delta.get("type") == "text_delta":
                    chunk = delta.get("text", "")
                    if chunk:
                        await on_event("token", {"text": chunk})
            continue

        if isinstance(message, AssistantMessage):
            for block in message.content or []:
                if isinstance(block, ToolUseBlock):
                    tool_names_by_id[block.id] = block.name
                    if emit_tool_events and on_event is not None:
                        await on_event("tool_call", {"name": block.name, "input": block.input})
            continue

        if isinstance(message, UserMessage):
            # UserMessage here typically carries tool_result blocks.
            if not emit_tool_events or on_event is None:
                continue
            content = message.content if isinstance(message.content, list) else []
            for block in content:
                if isinstance(block, ToolResultBlock):
                    preview = ""
                    if isinstance(block.content, str):
                        preview = block.content
                    elif isinstance(block.content, list):
                        for c in block.content:
                            if isinstance(c, dict) and c.get("type") == "text":
                                preview += c.get("text", "")
                    name = tool_names_by_id.get(block.tool_use_id, "")
                    await on_event("tool_result", {"name": name, "preview": preview[:300]})
            continue

        if isinstance(message, ResultMessage):
            text = message.result or ""
            result_info = {
                "duration_ms": message.duration_ms,
                "cost_usd": message.total_cost_usd,
                "num_turns": message.num_turns,
                "session_id": message.session_id,
                "usage": message.usage or {},
            }
            capture_response(result_info)

    usage = result_info.get("usage", {})
    return LLMResult(
        text=text,
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        cache_read_input_tokens=usage.get("cache_read_input_tokens", 0),
        cache_creation_input_tokens=usage.get("cache_creation_input_tokens", 0),
        cost_usd=result_info.get("cost_usd"),
    )


async def call_claude_sdk_simple(
    model_id: str,
    api_key: str,
    system: str,
    messages: list[dict],
    on_event: ToolEventCallback | None = None,
) -> LLMResult:
    """Chat mode: single turn, no tools."""
    prompt = _messages_to_prompt(messages)
    return await _call_sdk(
        prompt=prompt,
        model=model_id or None,
        system_prompt=system,
        allowed_tools=[],
        max_turns=1,
        on_event=on_event,
    )


def _make_sdk_tool(
    tool_def: dict,
    tool_dispatcher: ToolDispatcher,
    on_event: ToolEventCallback | None,
    log: list[dict],
):
    """Wrap a langosh tool definition as an in-process SDK MCP tool.

    When the SDK routes a call to this tool, we emit on_event callbacks
    and delegate to `tool_dispatcher` (which may apply approvals). The
    call is appended to `log` so the caller can return it as tool_calls.
    """
    tool_name = tool_def["name"]
    description = tool_def["description"]
    schema = tool_def["input_schema"]

    @tool(tool_name, description, schema)
    async def _wrapper(args):
        if on_event:
            await on_event("tool_call", {"name": tool_name, "input": args})
        try:
            result_str = await tool_dispatcher(tool_name, args)
        except Exception as e:
            result_str = f"Error in {tool_name}: {e}"
        log.append({
            "name": tool_name,
            "input": args,
            "result_preview": result_str[:300],
        })
        if on_event:
            await on_event("tool_result", {"name": tool_name, "result_preview": result_str[:300]})
        return {"content": [{"type": "text", "text": result_str}]}

    return _wrapper


async def call_claude_sdk_with_tools(
    model_id: str,
    api_key: str,
    system: str,
    messages: list[dict],
    tools: list[dict],
    tool_dispatcher: ToolDispatcher,
    on_event: ToolEventCallback | None = None,
    max_tool_turns: int | None = None,
    sub_mode: str = "auto",
) -> LLMResult:
    """Multi-turn call with tool-use.

    When `tools` is non-empty, each tool is exposed to the SDK via an
    in-process MCP server; calls route back to `tool_dispatcher`. This
    preserves our approval widget and per-tool event callbacks.

    When `tools` is empty, falls back to the SDK's own built-in tools
    (Read/Write/Edit/Bash/Glob/Grep) — only useful for raw code mode
    without any custom tool set.
    """
    _require_sdk()
    prompt = _messages_to_prompt(messages)

    if not tools:
        return await _call_sdk(
            prompt=prompt,
            model=model_id or None,
            system_prompt=system,
            allowed_tools=_CODE_TOOLS,
            max_turns=max_tool_turns or 20,
            permission_mode=_PERMISSION_MAP.get(sub_mode, "acceptEdits"),
            on_event=on_event,
        )

    tool_calls_log: list[dict] = []
    sdk_tools = [_make_sdk_tool(t, tool_dispatcher, on_event, tool_calls_log) for t in tools]
    mcp_server = create_sdk_mcp_server(name=_MCP_SERVER_NAME, tools=sdk_tools)
    allowed_tools = [f"mcp__{_MCP_SERVER_NAME}__{t['name']}" for t in tools]

    result = await _call_sdk(
        prompt=prompt,
        model=model_id or None,
        system_prompt=system,
        allowed_tools=allowed_tools,
        mcp_servers={_MCP_SERVER_NAME: mcp_server},
        max_turns=max_tool_turns or 20,
        # bypassPermissions: tool_dispatcher (via make_guarded_dispatcher)
        # runs our own approval widget; we don't want the SDK adding another.
        permission_mode="bypassPermissions",
        on_event=on_event,
        # Tool events already emitted by the MCP wrapper — don't duplicate
        # from the message-iteration path.
        emit_tool_events=False,
    )
    result["tool_calls"] = tool_calls_log
    return result
