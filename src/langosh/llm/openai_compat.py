"""OpenAI-compatible multi-turn tool-calling loop (OpenAI, DeepSeek, xAI)."""

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
    """Multi-turn OpenAI-compatible call with function-calling."""
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
        resp = await client.chat.completions.create(**request_body)
        capture_response(resp.model_dump())
        usage = resp.usage
        total_input += usage.prompt_tokens if usage else 0
        total_output += usage.completion_tokens if usage else 0

        choice = resp.choices[0]

        def _result(text: str) -> LLMResult:
            return LLMResult(
                text=text,
                input_tokens=total_input,
                output_tokens=total_output,
                tool_calls=tool_calls_log,
            )

        if choice.finish_reason != "tool_calls":
            return _result(choice.message.content or "")

        if turn >= max_tool_turns:
            text = choice.message.content or "[Reached tool-use turn cap]"
            text += "\n\n_Note: Stopped after reaching the tool-use turn limit._"
            return _result(text)

        conv.append(choice.message.model_dump())
        for tc in choice.message.tool_calls or []:
            args = (
                _json.loads(tc.function.arguments)
                if isinstance(tc.function.arguments, str)
                else tc.function.arguments
            )
            if on_event:
                await on_event("tool_call", {"name": tc.function.name, "input": args})
            result_str = await tool_dispatcher(tc.function.name, args)
            tool_calls_log.append({
                "name": tc.function.name,
                "input": args,
                "result_preview": result_str[:300],
            })
            if on_event:
                await on_event(
                    "tool_result", {"name": tc.function.name, "result_preview": result_str[:300]}
                )
            conv.append({"role": "tool", "tool_call_id": tc.id, "content": result_str})

    return _result("")


async def call_openai_simple(
    provider: str,
    model_id: str,
    api_key: str,
    system: str,
    messages: list[dict],
) -> LLMResult:
    """Single-turn OpenAI-compatible call without tools."""
    _require_sdk()
    settings = get_settings()
    api_key = api_key or settings.openai_api_key

    client = openai.AsyncOpenAI(api_key=api_key, base_url=OPENAI_BASE_URLS.get(provider))
    oai_messages = [{"role": "system", "content": system}] + messages
    request_body = {"model": model_id, "max_tokens": settings.max_tokens, "messages": oai_messages}
    capture_request(request_body)
    resp = await client.chat.completions.create(**request_body)
    capture_response(resp.model_dump())
    usage = resp.usage
    return LLMResult(
        text=resp.choices[0].message.content or "",
        input_tokens=usage.prompt_tokens if usage else 0,
        output_tokens=usage.completion_tokens if usage else 0,
    )
