"""Unified LLM provider dispatcher — routes to Anthropic, OpenAI, or Bedrock."""

import logging

from ..config import DEFAULT_MODELS, get_settings
from .types import LLMResult, ToolDispatcher, ToolEventCallback

logger = logging.getLogger(__name__)


def _resolve(provider: str | None, model_id: str | None, api_key: str | None) -> tuple[str, str, str]:
    """Resolve provider, model, and API key from explicit args or config defaults."""
    settings = get_settings()
    provider = provider or settings.default_provider
    model_id = model_id or settings.default_model or DEFAULT_MODELS.get(provider, "")
    if not api_key:
        if provider == "anthropic":
            api_key = settings.anthropic_api_key
        elif provider in ("openai", "deepseek", "xai"):
            api_key = settings.openai_api_key
    return provider, model_id, api_key or ""


async def call_with_tools(
    provider: str | None,
    model_id: str | None,
    api_key: str | None,
    system: str,
    messages: list[dict],
    tools: list[dict],
    tool_dispatcher: ToolDispatcher,
    on_event: ToolEventCallback | None = None,
    max_tool_turns: int | None = None,
    **kwargs,
) -> LLMResult:
    """Multi-turn LLM call with tool-use. Routes to the appropriate provider."""
    provider, model_id, api_key = _resolve(provider, model_id, api_key)

    if provider == "claude_sdk":
        from .claude_sdk import call_claude_sdk_with_tools

        return await call_claude_sdk_with_tools(
            model_id, api_key, system, messages, tools,
            tool_dispatcher, on_event, max_tool_turns,
            sub_mode=kwargs.get("sub_mode", "auto"),
        )
    if provider == "anthropic":
        from .anthropic import call_anthropic_with_tools

        return await call_anthropic_with_tools(
            model_id, api_key, system, messages, tools,
            tool_dispatcher, on_event, max_tool_turns,
        )
    if provider in ("openai", "deepseek", "xai"):
        from .openai_compat import call_openai_with_tools

        return await call_openai_with_tools(
            provider, model_id, api_key, system, messages, tools,
            tool_dispatcher, on_event, max_tool_turns,
        )
    if provider == "bedrock_converse":
        from .bedrock import call_bedrock_with_tools

        return await call_bedrock_with_tools(
            model_id, api_key, system, messages, tools,
            tool_dispatcher, on_event, max_tool_turns,
        )
    raise ValueError(f"No tool-calling support for provider: {provider}")


async def call_llm_simple(
    provider: str | None,
    model_id: str | None,
    api_key: str | None,
    system: str,
    messages: list[dict],
    on_event: ToolEventCallback | None = None,
) -> LLMResult:
    """Single-turn LLM call without tools. Routes to the appropriate provider."""
    provider, model_id, api_key = _resolve(provider, model_id, api_key)

    if provider == "claude_sdk":
        from .claude_sdk import call_claude_sdk_simple

        return await call_claude_sdk_simple(model_id, api_key, system, messages, on_event)

    if provider == "anthropic":
        from .anthropic import call_anthropic_simple

        return await call_anthropic_simple(model_id, api_key, system, messages, on_event)
    if provider in ("openai", "deepseek", "xai"):
        from .openai_compat import call_openai_simple

        return await call_openai_simple(provider, model_id, api_key, system, messages, on_event)
    if provider == "bedrock_converse":
        from .bedrock import call_bedrock_simple

        return await call_bedrock_simple(model_id, api_key, system, messages, on_event)
    raise ValueError(f"Unsupported provider: {provider}")
