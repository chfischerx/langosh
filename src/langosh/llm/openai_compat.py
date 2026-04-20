"""OpenAI-compatible multi-turn tool-calling loop (OpenAI, DeepSeek, xAI) with streaming."""

import json as _json
import logging

from ..config import get_settings
from .debug import capture_request, capture_response
from .types import LLMResult, ToolDispatcher, ToolEventCallback

logger = logging.getLogger(__name__)

try:
    import openai
except ImportError:
    openai = None  # type: ignore[assignment]

OPENAI_BASE_URLS: dict[str, str | None] = {
    "openai": None,
    "deepseek": "https://api.deepseek.com",
    "xai": "https://api.x.ai/v1",
}


def _require_sdk() -> None:
    if openai is None:
        raise ImportError(
            "The 'openai' package is required for OpenAI-compatible providers. "
            "Install it with: pip install langosh[openai]"
        )


def tools_to_openai_format(tools: list[dict]) -> list[dict]:
    """Convert Anthropic-style tool schemas to OpenAI function-calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in tools
    ]


async def _stream_turn(client, request_body: dict, on_event):
    """Stream one completion; emit token events; return (content_text, tool_calls_list, finish_reason, usage).

    tool_calls_list is a list of dicts: {id, name, arguments_str}.
    """
    request_body = {**request_body, "stream": True, "stream_options": {"include_usage": True}}
    resp = await client.chat.completions.create(**request_body)

    content = ""
    tc_acc: dict[int, dict] = {}  # index -> {id, name, arguments}
    finish_reason: str | None = None
    usage = None

    async for chunk in resp:
        if chunk.choices:
            choice = chunk.choices[0]
            delta = choice.delta
            # Streaming text
            if getattr(delta, "content", None):
                content += delta.content
                if on_event is not None:
                    await on_event("token", {"text": delta.content})
            # Streaming tool calls (partial JSON)
            if getattr(delta, "tool_calls", None):
                for tc in delta.tool_calls:
                    idx = tc.index
                    slot = tc_acc.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                    if getattr(tc, "id", None):
                        slot["id"] = tc.id
                    fn = getattr(tc, "function", None)
                    if fn is not None:
                        if getattr(fn, "name", None):
                            slot["name"] = fn.name
                        if getattr(fn, "arguments", None):
                            slot["arguments"] += fn.arguments
            if choice.finish_reason:
                finish_reason = choice.finish_reason
        if getattr(chunk, "usage", None):
            usage = chunk.usage

    tool_calls = [tc_acc[k] for k in sorted(tc_acc.keys())]
    return content, tool_calls, finish_reason, usage


async def call_openai_with_tools(
    provider: str,
    model_id: str,
    api_key: str,
    system: str,
    messages: list[dict],
    tools: list[dict],
    tool_dispatcher: ToolDispatcher,
    on_event: ToolEventCallback | None = None,
    max_tool_turns: int | None = None,
) -> LLMResult:
    """Multi-turn OpenAI-compatible call with streaming function-calling."""
    _require_sdk()
    settings = get_settings()
    api_key = api_key or settings.openai_api_key
    max_tool_turns = max_tool_turns if max_tool_turns is not None else settings.max_tool_turns

    client = openai.AsyncOpenAI(api_key=api_key, base_url=OPENAI_BASE_URLS.get(provider))
    total_input = 0
    total_output = 0
    tool_calls_log: list[dict] = []
    oai_tools = tools_to_openai_format(tools)

    conv: list[dict] = [{"role": "system", "content": system}] + list(messages)

    for turn in range(max_tool_turns + 1):
        request_body = {"model": model_id, "max_tokens": settings.max_tokens, "messages": conv, "tools": oai_tools}
        capture_request(request_body)
        content, tool_calls, finish_reason, usage = await _stream_turn(client, request_body, on_event)
        capture_response({
            "finish_reason": finish_reason,
            "usage": usage.model_dump() if usage else None,
            "content": content,
            "tool_calls": tool_calls,
        })
        if usage is not None:
            total_input += usage.prompt_tokens or 0
            total_output += usage.completion_tokens or 0

        def _result(text: str) -> LLMResult:
            return LLMResult(
                text=text,
                input_tokens=total_input,
                output_tokens=total_output,
                tool_calls=tool_calls_log,
            )

        if finish_reason != "tool_calls":
            return _result(content or "")

        if turn >= max_tool_turns:
            text = content or "[Reached tool-use turn cap]"
            text += "\n\n_Note: Stopped after reaching the tool-use turn limit._"
            return _result(text)

        # Add assistant message with tool calls
        assistant_msg = {
            "role": "assistant",
            "content": content or None,
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["arguments"]},
                }
                for tc in tool_calls
            ],
        }
        conv.append(assistant_msg)

        for tc in tool_calls:
            try:
                args = _json.loads(tc["arguments"]) if tc["arguments"] else {}
            except _json.JSONDecodeError:
                args = {}
            if on_event:
                await on_event("tool_call", {"name": tc["name"], "input": args})
            result_str = await tool_dispatcher(tc["name"], args)
            tool_calls_log.append({
                "name": tc["name"],
                "input": args,
                "result_preview": result_str[:300],
            })
            if on_event:
                await on_event(
                    "tool_result", {"name": tc["name"], "result_preview": result_str[:300]}
                )
            conv.append({"role": "tool", "tool_call_id": tc["id"], "content": result_str})

    return _result("")


async def call_openai_simple(
    provider: str,
    model_id: str,
    api_key: str,
    system: str,
    messages: list[dict],
    on_event: ToolEventCallback | None = None,
) -> LLMResult:
    """Single-turn OpenAI-compatible call without tools, streaming tokens."""
    _require_sdk()
    settings = get_settings()
    api_key = api_key or settings.openai_api_key

    client = openai.AsyncOpenAI(api_key=api_key, base_url=OPENAI_BASE_URLS.get(provider))
    oai_messages = [{"role": "system", "content": system}] + messages
    request_body = {"model": model_id, "max_tokens": settings.max_tokens, "messages": oai_messages}
    capture_request(request_body)
    content, _, _, usage = await _stream_turn(client, request_body, on_event)
    capture_response({"content": content, "usage": usage.model_dump() if usage else None})
    return LLMResult(
        text=content or "",
        input_tokens=usage.prompt_tokens if usage else 0,
        output_tokens=usage.completion_tokens if usage else 0,
    )
