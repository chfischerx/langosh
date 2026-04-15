"""Claude Agent SDK provider.

Chat mode: allowed_tools=[], max_turns=1 (plain chat, no tools)
Code mode: allowed_tools=built-in tools, max_turns=20 (SDK handles tool execution)

No API key needed — uses the user's Claude subscription.
"""

import logging
import os

from .debug import capture_request, capture_response
from .types import LLMResult, ToolDispatcher, ToolEventCallback

logger = logging.getLogger(__name__)

try:
    from claude_agent_sdk import (
        ClaudeAgentOptions,
        ResultMessage,
        query,
    )
except ImportError:
    query = None  # type: ignore[assignment]

# Built-in SDK tools for code mode
_CODE_TOOLS = ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]

# Map our sub-modes to SDK permission modes
_PERMISSION_MAP = {
    "plan": "plan",
    "auto": "acceptEdits",
    "edit": "bypassPermissions",
}


def _require_sdk() -> None:
    if query is None:
        raise ImportError(
            "The 'claude-agent-sdk' package is required for the Claude SDK provider. "
            "Install it with: pip install langosh[claude-sdk]"
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
    max_turns: int = 1,
    permission_mode: str | None = None,
) -> LLMResult:
    """Call the Claude Agent SDK."""
    _require_sdk()

    kwargs: dict = {
        "model": model,
        "max_turns": max_turns,
        "cwd": os.getcwd(),
    }
    if system_prompt:
        kwargs["system_prompt"] = system_prompt
    if allowed_tools is not None:
        kwargs["allowed_tools"] = allowed_tools
    if permission_mode:
        kwargs["permission_mode"] = permission_mode

    options = ClaudeAgentOptions(**kwargs)

    capture_request({
        "prompt": prompt,
        "model": model,
        "system_prompt": system_prompt,
        "allowed_tools": allowed_tools,
        "max_turns": max_turns,
        "permission_mode": permission_mode,
    })

    text = ""
    result_info: dict = {}

    async for message in query(prompt=prompt, options=options):
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
        cost_usd=result_info.get("cost_usd"),
    )


async def call_claude_sdk_simple(
    model_id: str,
    api_key: str,
    system: str,
    messages: list[dict],
) -> LLMResult:
    """Chat mode: single turn, no tools."""
    prompt = _messages_to_prompt(messages)
    return await _call_sdk(
        prompt=prompt,
        model=model_id or None,
        system_prompt=system,
        allowed_tools=[],
        max_turns=1,
    )


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
    """Code mode: SDK handles tool execution with built-in tools."""
    prompt = _messages_to_prompt(messages)
    return await _call_sdk(
        prompt=prompt,
        model=model_id or None,
        system_prompt=system,
        allowed_tools=_CODE_TOOLS,
        max_turns=max_tool_turns or 20,
        permission_mode=_PERMISSION_MAP.get(sub_mode, "acceptEdits"),
    )
