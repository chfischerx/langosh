"""Anthropic Claude multi-turn tool-calling loop with prompt caching."""

import logging

from ..config import get_settings
from .debug import capture_request, capture_response
from .types import LLMResult, ToolDispatcher, ToolEventCallback

logger = logging.getLogger(__name__)

try:
    import anthropic
except ImportError:
    anthropic = None  # type: ignore[assignment]


def _require_sdk() -> None:
    if anthropic is None:
        raise ImportError(
            "The 'anthropic' package is required for the Anthropic provider. "
            "Install it with: pip install langosh[anthropic]"
        )


async def call_anthropic_with_tools(
    model_id: str,
    api_key: str,
    system: str,
    messages: list[dict],
    tools: list[dict],
    tool_dispatcher: ToolDispatcher,
    on_event: ToolEventCallback | None = None,
    max_tool_turns: int | None = None,
) -> LLMResult:
    """Multi-turn Claude call with tool-use and prompt caching."""
    _require_sdk()
    settings = get_settings()
    api_key = api_key or settings.anthropic_api_key
    max_tool_turns = max_tool_turns if max_tool_turns is not None else settings.max_tool_turns

    client = anthropic.AsyncAnthropic(api_key=api_key)
    total_input = 0
    total_output = 0
    total_cache_read = 0
    total_cache_creation = 0
    tool_calls_log: list[dict] = []

    conv = list(messages)
    cached_system = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]

    for turn in range(max_tool_turns + 1):
        request_body = {
            "model": model_id,
            "max_tokens": settings.max_tokens,
            "system": cached_system,
            "messages": conv,
            "tools": tools,
        }
        capture_request(request_body)
        resp = await client.messages.create(**request_body)
        capture_response({"stop_reason": resp.stop_reason, "usage": vars(resp.usage), "content": [vars(b) if hasattr(b, "__dict__") else b for b in resp.content]})
        total_input += resp.usage.input_tokens or 0
        total_output += resp.usage.output_tokens or 0
        total_cache_read += getattr(resp.usage, "cache_read_input_tokens", 0) or 0
        total_cache_creation += getattr(resp.usage, "cache_creation_input_tokens", 0) or 0

        def _result(text: str) -> LLMResult:
            return LLMResult(
                text=text,
                input_tokens=total_input,
                output_tokens=total_output,
                cache_read_input_tokens=total_cache_read,
                cache_creation_input_tokens=total_cache_creation,
                tool_calls=tool_calls_log,
            )

        if resp.stop_reason != "tool_use":
            text_parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
            return _result("\n".join(text_parts).strip())

        if turn >= max_tool_turns:
            text_parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
            text = ("\n".join(text_parts) or "[Reached tool-use turn cap]").strip()
            text += "\n\n_Note: Stopped after reaching the tool-use turn limit._"
            return _result(text)

        conv.append({"role": "assistant", "content": resp.content})
        tool_results = []
        for block in resp.content:
            if getattr(block, "type", None) != "tool_use":
                continue
            if on_event:
                await on_event("tool_call", {"name": block.name, "input": block.input or {}})
            result_str = await tool_dispatcher(block.name, block.input or {})
            tool_calls_log.append({
                "name": block.name,
                "input": block.input or {},
                "result_preview": result_str[:300],
            })
            if on_event:
                await on_event("tool_result", {"name": block.name, "result_preview": result_str[:300]})
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result_str,
            })
        conv.append({"role": "user", "content": tool_results})

    return _result("")


async def call_anthropic_simple(
    model_id: str,
    api_key: str,
    system: str,
    messages: list[dict],
) -> LLMResult:
    """Single-turn Claude call without tools."""
    _require_sdk()
    settings = get_settings()
    api_key = api_key or settings.anthropic_api_key

    client = anthropic.AsyncAnthropic(api_key=api_key)
    request_body = {
        "model": model_id,
        "max_tokens": settings.max_tokens,
        "system": system,
        "messages": messages,
    }
    capture_request(request_body)
    resp = await client.messages.create(**request_body)
    capture_response({"stop_reason": resp.stop_reason, "usage": vars(resp.usage), "content": [vars(b) if hasattr(b, "__dict__") else b for b in resp.content]})
    return LLMResult(
        text=resp.content[0].text,
        input_tokens=resp.usage.input_tokens,
        output_tokens=resp.usage.output_tokens,
    )
