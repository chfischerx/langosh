"""Agent editor — LLM conversation for modifying agents with builder tools."""

import asyncio
import json
import os
import time

import langosh.state as state

from ..context import apply_window
from ..input import model_display_name
from ..rendering import print_renderables, render_semantic
from .editor_tools import READ_TOOLS, TOOLS, WRITE_TOOLS, make_editor_dispatch
_AGENTS_DATA_DIR = os.path.join(os.path.expanduser("~"), ".langosh", "agents")


def _history_path(agent_id: str) -> str:
    return os.path.join(_AGENTS_DATA_DIR, agent_id, "history.json")


def load_agent_history(agent_id: str) -> tuple[list[dict], str]:
    """Load conversation history for an agent."""
    path = _history_path(agent_id)
    if not os.path.isfile(path):
        return [], ""
    try:
        with open(path) as f:
            data = json.load(f)
        return data.get("messages", []), data.get("summary", "")
    except (json.JSONDecodeError, OSError):
        return [], ""


def save_agent_history(agent_id: str) -> None:
    """Save current agent conversation history."""
    path = _history_path(agent_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump({"messages": state.agent_messages, "summary": state.agent_summary}, f, ensure_ascii=False)


def clear_agent_history(agent_id: str) -> None:
    """Clear agent conversation history."""
    path = _history_path(agent_id)
    if os.path.isfile(path):
        os.remove(path)


def _make_guarded_dispatcher(agent_id: str):
    """Create a guarded dispatcher for editor tools respecting agent_sub_mode."""
    from ..llm.tools import WRITE_TOOLS as _  # noqa — just for the approval widget import
    from ..llm.tools import make_guarded_dispatcher as _make_base_guarded

    dispatch = make_editor_dispatch(agent_id)

    # Build a combined dispatcher that routes to editor tools
    async def _dispatch(name: str, args: dict) -> str:
        fn = dispatch.get(name)
        if not fn:
            return f"Unknown tool: {name}"
        try:
            return await fn(args)
        except Exception as e:
            return f"Error executing {name}: {e}"

    # Wrap with approval based on sub_mode
    def _needs_approval(tool_name: str) -> bool:
        if state.agent_sub_mode == "edit":
            return False
        if state.agent_sub_mode == "plan":
            return True
        # auto: reads auto-approved, writes need approval
        return tool_name in WRITE_TOOLS

    always_allowed: set[str] = set()

    async def guarded_dispatch(name: str, args: dict) -> str:
        if _needs_approval(name) and name not in always_allowed:
            from ..llm.tools import _show_approval_widget

            choice = await asyncio.to_thread(_show_approval_widget, name, args, state.console)
            if choice == "deny":
                state.console.print(f"[dim]  ✗ {name} denied[/dim]")
                return "Tool call denied by user."
            if choice == "always":
                always_allowed.add(name)
            state.console.print(f"[dim]  ✓ {name} approved[/dim]")
        return await _dispatch(name, args)

    return guarded_dispatch


def send_edit_query(text: str) -> None:
    """Send an edit instruction to the LLM with builder tools."""
    from ..config import DEFAULT_MODELS, get_settings
    from ..llm import call_with_tools
    from ..llm.prompts.builder import BUILDER_SYSTEM_PROMPT
    from ..queries import format_elapsed

    agent_id = state.active_agent_id
    if not agent_id:
        state.console.print("[red]No agent selected. Use /select first.[/red]")
        return

    settings = get_settings()
    provider = state.active_model["provider"] or settings.default_provider
    model_id = state.active_model["model_id"] or settings.default_model or DEFAULT_MODELS.get(provider, "")

    # Add user message to history
    state.agent_messages.append({"role": "user", "content": text})
    messages_to_send = apply_window("agent", state.agent_messages, provider, model_id)

    start = time.monotonic()
    try:
        with state.console.status(f"[dim]Calling {model_display_name() or model_id}...[/dim]") as status:
            async def _on_event(event_type: str, data: dict) -> None:
                name = data.get("name", "")
                if event_type == "tool_call":
                    status.stop()
                    state.console.print(f"[dim]  ↳ calling {name}...[/dim]")
                elif event_type == "tool_result":
                    state.console.print(f"[dim]  ↳ {name} done[/dim]")
                    status.start()

            result = asyncio.run(
                call_with_tools(
                    provider=provider,
                    model_id=model_id,
                    api_key=None,
                    system=BUILDER_SYSTEM_PROMPT,
                    messages=messages_to_send,
                    tools=TOOLS,
                    tool_dispatcher=_make_guarded_dispatcher(agent_id),
                    on_event=_on_event,
                    sub_mode=state.agent_sub_mode,
                )
            )
    except KeyboardInterrupt:
        if state.agent_messages and state.agent_messages[-1].get("role") == "user":
            state.agent_messages.pop()
        state.console.print("\n[yellow]Interrupted.[/yellow]")
        return
    elapsed = time.monotonic() - start

    # Add assistant response and save
    state.agent_messages.append({"role": "assistant", "content": result["text"]})
    save_agent_history(agent_id)

    # Update debug store
    state.last_debug.clear()
    state.last_debug.update({
        "mode": "agents:edit",
        "provider": provider,
        "model_id": model_id,
        "model_name": model_display_name() or model_id,
        "system_prompt": BUILDER_SYSTEM_PROMPT,
        "messages_sent": messages_to_send,
        "message_count": len(messages_to_send),
        "tools": [t["name"] for t in TOOLS],
        "sub_mode": state.agent_sub_mode,
        "response_text": result["text"],
        "input_tokens": result["input_tokens"],
        "output_tokens": result["output_tokens"],
        "cache_read_tokens": result.get("cache_read_input_tokens", 0),
        "cache_creation_tokens": result.get("cache_creation_input_tokens", 0),
        "tool_calls": result.get("tool_calls", []),
        "elapsed": elapsed,
    })

    print_renderables(state.console, render_semantic(result["text"]))

    tool_calls = result.get("tool_calls", [])
    tool_info = f" | {len(tool_calls)} tool calls" if tool_calls else ""
    cost = result.get("cost_usd")
    cost_info = f" | ${cost:.4f}" if cost else ""
    turns = len([m for m in state.agent_messages if m["role"] == "user"])
    state.console.print(
        f"\n[dim]{format_elapsed(elapsed)} | "
        f"{result['input_tokens']} ↑ / {result['output_tokens']} ↓{tool_info}{cost_info} | "
        f"turn {turns}[/dim]"
    )
