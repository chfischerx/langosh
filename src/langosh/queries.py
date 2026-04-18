"""LLM query functions for chat and code modes."""

import asyncio
import time

import langosh.state as state

from .context import apply_window
from .input import model_display_name
from .rendering import print_renderables, render_semantic


def format_elapsed(seconds: float) -> str:
    """Format elapsed time as Xm Ys or Xs."""
    if seconds >= 60:
        m = int(seconds) // 60
        s = int(seconds) % 60
        return f"{m}m {s}s"
    return f"{seconds:.1f}s"


def send_query(text: str) -> None:
    """Send text as an LLM prompt using the active model with conversation history."""
    from .config import DEFAULT_MODELS, get_settings
    from .history import save_history
    from .llm import call_llm_simple
    from .llm.prompts.chat import CHAT_SYSTEM_PROMPT

    settings = get_settings()
    provider = state.active_model["provider"] or settings.default_provider
    model_id = state.active_model["model_id"] or settings.default_model or DEFAULT_MODELS.get(provider, "")

    state.chat_messages.append({"role": "user", "content": text})
    messages_to_send = apply_window("chat", state.chat_messages, provider, model_id)

    start = time.monotonic()
    try:
        result = asyncio.run(
            call_llm_simple(
                provider=provider,
                model_id=model_id,
                api_key=None,
                system=CHAT_SYSTEM_PROMPT,
                messages=messages_to_send,
            )
        )
    except KeyboardInterrupt:
        if state.chat_messages and state.chat_messages[-1].get("role") == "user":
            state.chat_messages.pop()
        state.console.print("\n[yellow]Interrupted.[/yellow]")
        return
    elapsed = time.monotonic() - start

    state.chat_messages.append({"role": "assistant", "content": result["text"]})
    save_history("chat", state.chat_messages, state.chat_summary)

    state.last_debug.clear()
    state.last_debug.update({
        "mode": "chat",
        "provider": provider,
        "model_id": model_id,
        "model_name": model_display_name() or model_id,
        "system_prompt": CHAT_SYSTEM_PROMPT,
        "messages_sent": messages_to_send,
        "message_count": len(messages_to_send),
        "tools": None,
        "sub_mode": None,
        "response_text": result["text"],
        "input_tokens": result["input_tokens"],
        "output_tokens": result["output_tokens"],
        "cache_read_tokens": result.get("cache_read_input_tokens", 0),
        "cache_creation_tokens": result.get("cache_creation_input_tokens", 0),
        "tool_calls": [],
        "elapsed": elapsed,
    })

    print_renderables(state.console, render_semantic(result["text"]))
    turns = len([m for m in state.chat_messages if m["role"] == "user"])
    state.console.print(
        f"\n[dim]{format_elapsed(elapsed)} | "
        f"{result['input_tokens']} ↑ / {result['output_tokens']} ↓ | "
        f"turn {turns}[/dim]"
    )


def send_code_query(text: str) -> None:
    """Send text as an LLM prompt with tool-calling using the active model."""
    from .config import DEFAULT_MODELS, get_settings
    from .history import save_history
    from .llm import call_with_tools
    from .llm.prompts.code import build_code_system_prompt
    from .llm.tools import ALL_TOOLS, make_guarded_dispatcher

    settings = get_settings()
    provider = state.active_model["provider"] or settings.default_provider
    model_id = state.active_model["model_id"] or settings.default_model or DEFAULT_MODELS.get(provider, "")

    state.code_messages.append({"role": "user", "content": text})

    system_prompt = build_code_system_prompt()
    messages_to_send = apply_window("code", state.code_messages, provider, model_id)

    async def _on_event(event_type: str, data: dict) -> None:
        name = data.get("name", "")
        if event_type == "tool_call":
            state.console.print(f"[dim]  ↳ calling {name}...[/dim]")
        elif event_type == "tool_result":
            preview = data.get("result_preview", "")[:100]
            state.console.print(f"[dim]  ↳ {name} done ({len(preview)} chars)[/dim]")

    start = time.monotonic()
    state.console.print(f"[dim]Calling {model_display_name() or model_id}...[/dim]")

    try:
        result = asyncio.run(
            call_with_tools(
                provider=provider,
                model_id=model_id,
                api_key=None,
                system=system_prompt,
                messages=messages_to_send,
                tools=ALL_TOOLS,
                tool_dispatcher=make_guarded_dispatcher(state.code_sub_mode, state.console),
                on_event=_on_event,
                sub_mode=state.code_sub_mode,
            )
        )
    except KeyboardInterrupt:
        if state.code_messages and state.code_messages[-1].get("role") == "user":
            state.code_messages.pop()
        state.console.print("\n[yellow]Interrupted.[/yellow]")
        return
    elapsed = time.monotonic() - start

    state.code_messages.append({"role": "assistant", "content": result["text"]})
    save_history("code", state.code_messages, state.code_summary)

    tool_calls = result.get("tool_calls", [])

    state.last_debug.clear()
    state.last_debug.update({
        "mode": "code",
        "provider": provider,
        "model_id": model_id,
        "model_name": model_display_name() or model_id,
        "system_prompt": system_prompt,
        "messages_sent": messages_to_send,
        "message_count": len(messages_to_send),
        "tools": [t["name"] for t in ALL_TOOLS],
        "sub_mode": state.code_sub_mode,
        "response_text": result["text"],
        "input_tokens": result["input_tokens"],
        "output_tokens": result["output_tokens"],
        "cache_read_tokens": result.get("cache_read_input_tokens", 0),
        "cache_creation_tokens": result.get("cache_creation_input_tokens", 0),
        "tool_calls": tool_calls,
        "elapsed": elapsed,
    })

    print_renderables(state.console, render_semantic(result["text"]))

    tool_info = f" | {len(tool_calls)} tool calls" if tool_calls else ""
    cost = result.get("cost_usd")
    cost_info = f" | ${cost:.4f}" if cost else ""
    turns = len([m for m in state.code_messages if m["role"] == "user"])
    state.console.print(
        f"\n[dim]{format_elapsed(elapsed)} | "
        f"{result['input_tokens']} ↑ / {result['output_tokens']} ↓{tool_info}{cost_info} | "
        f"turn {turns}[/dim]"
    )
