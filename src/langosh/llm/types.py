"""Shared type definitions for LLM providers."""

from typing import Awaitable, Callable, NotRequired, TypedDict

# Callback that executes a tool and returns its string result.
ToolDispatcher = Callable[[str, dict], Awaitable[str]]

# Callback that fires on each tool call/result during multi-turn loops.
ToolEventCallback = Callable[[str, dict], Awaitable[None]]


class LLMResult(TypedDict):
    text: str
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: NotRequired[int]
    cache_creation_input_tokens: NotRequired[int]
    tool_calls: NotRequired[list[dict]]
    cost_usd: NotRequired[float | None]
