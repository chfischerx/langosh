"""Agent editor — LLM conversation for modifying graphs via builder tools."""

import asyncio
import time

import langosh.state as state

from ..context import apply_window
from ..input import model_display_name
from ..rendering import print_renderables, render_semantic
from . import codegen, registry
from ..llm.tools.docs_tools import DISPATCH as _DOCS_DISPATCH
from ..llm.tools.docs_tools import TOOLS as _DOCS_TOOLS
from ..llm.tools.subagent_tools import DISPATCH as _SUBAGENT_DISPATCH
from ..llm.tools.subagent_tools import TOOLS as _SUBAGENT_TOOLS
from .editor_tools import TOOLS as _EDITOR_TOOLS
from .editor_tools import WRITE_TOOLS, make_editor_dispatch

TOOLS = _EDITOR_TOOLS + _DOCS_TOOLS + _SUBAGENT_TOOLS


def _make_guarded_dispatcher(graph_id: str):
    """Create a guarded dispatcher for editor tools respecting agent_sub_mode."""
    editor_dispatch = make_editor_dispatch(graph_id)
    dispatch = {**editor_dispatch, **_DOCS_DISPATCH, **_SUBAGENT_DISPATCH}

    # Build a combined dispatcher that routes to editor tools + docs + subagents
    async def _dispatch(name: str, args: dict) -> str:
        fn = dispatch.get(name)
        if not fn:
            return f"Unknown tool: {name}"
        try:
            return await fn(args)
        except Exception as e:
            return f"Error executing {name}: {e}"

    # Read tools (docs + definition reads + subagent delegation) auto-approved.
    READ_TOOLS = {"read_definition", "list_functions", "read_function",
                  "docs_search", "docs_read", "spawn_subagent"}

    always_allowed: set[str] = set()

    async def guarded_dispatch(name: str, args: dict) -> str:
        # Reads always allowed
        if name in READ_TOOLS:
            return await _dispatch(name, args)
        # Edit mode and always-allowed tools skip approval
        if state.agent_sub_mode == "edit" or name in always_allowed:
            return await _dispatch(name, args)
        # Plan mode: writes denied outright
        if state.agent_sub_mode == "plan":
            state.console.print(f"[dim]  ✗ {name} denied (plan mode is read-only)[/dim]")
            return "Tool call denied: plan mode is read-only."
        # Auto mode: ask approval for writes
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
    from ..llm.prompts.builder import builder_system_prompt
    from ..queries import format_elapsed

    graph_id = state.active_graph_id
    if not graph_id:
        state.console.print("[red]No graph selected. Use /select first.[/red]")
        return

    settings = get_settings()
    provider = state.active_model["provider"] or settings.default_provider
    model_id = state.active_model["model_id"] or settings.default_model or DEFAULT_MODELS.get(provider, "")
    system_prompt = builder_system_prompt()

    # Add user message to history
    state.agent_messages.append({"role": "user", "content": text})
    messages_to_send = apply_window("agent", state.agent_messages, provider, model_id)

    from ..input import set_processing
    from ..llm.tools.subagent_tools import set_parent_on_event
    from ..queries import _format_tool_args
    token_count = {"n": 0}
    base_msg = f"Calling {model_display_name() or model_id}"

    async def _on_event(event_type: str, data: dict) -> None:
        name = data.get("name", "")
        if event_type == "token":
            chunk = data.get("text", "")
            if chunk:
                token_count["n"] += len(chunk)
                set_processing(f"{base_msg} ({token_count['n']} chars)")
        elif event_type == "status":
            text = data.get("text", "").strip()
            if text:
                state.console.print(f"[dim italic]  • {text}[/dim italic]")
        elif event_type == "tool_call":
            args_str = _format_tool_args(data.get("input", {}))
            state.console.print(f"[dim]  ↳ {name}([/dim][cyan]{args_str}[/cyan][dim])[/dim]")
        elif event_type == "tool_result":
            state.console.print(f"[dim]  ↳ {name} done[/dim]")

    set_parent_on_event(_on_event)

    start = time.monotonic()
    try:
        result = asyncio.run(
            call_with_tools(
                provider=provider,
                model_id=model_id,
                api_key=None,
                system=system_prompt,
                messages=messages_to_send,
                tools=TOOLS,
                tool_dispatcher=_make_guarded_dispatcher(graph_id),
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

    state.agent_messages.append({"role": "assistant", "content": result["text"]})

    # If the LLM wrote anything, regenerate the deployable Python module so
    # langgraph.json's pointer keeps matching the canonical JSON definition.
    tool_calls = result.get("tool_calls", [])
    wrote_anything = any(tc.get("name") in WRITE_TOOLS for tc in tool_calls)
    if wrote_anything:
        try:
            _regenerate_module(graph_id)
            state.console.print(
                f"[dim]  ↳ regenerated {registry.graph_dir(graph_id) / '__init__.py'} "
                "(restart langosh-server to pick up changes)[/dim]"
            )
        except Exception as e:
            state.console.print(f"[bold red]Codegen failed:[/bold red] {e}")

    # Update debug store
    state.last_debug.clear()
    state.last_debug.update({
        "mode": "agents:edit",
        "provider": provider,
        "model_id": model_id,
        "model_name": model_display_name() or model_id,
        "system_prompt": system_prompt,
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

    tool_info = f" | {len(tool_calls)} tool calls" if tool_calls else ""
    cost = result.get("cost_usd")
    cost_info = f" | ${cost:.4f}" if cost else ""
    turns = len([m for m in state.agent_messages if m["role"] == "user"])
    state.console.print(
        f"\n[dim]{format_elapsed(elapsed)} | "
        f"{result['input_tokens']} ↑ / {result['output_tokens']} ↓{tool_info}{cost_info} | "
        f"turn {turns}[/dim]"
    )


def _regenerate_module(graph_id: str) -> None:
    """Reload definition.json + functions/*.py from disk and re-emit the .py."""
    import json
    from pathlib import Path

    folder = registry.graph_dir(graph_id)
    def_path = folder / "definition.json"
    if not def_path.is_file():
        raise FileNotFoundError(f"No definition.json for {graph_id} at {def_path}")
    definition = json.loads(def_path.read_text())

    funcs_dir = folder / "functions"
    functions: list[dict] = []
    if funcs_dir.is_dir():
        for fn_path in sorted(Path(funcs_dir).glob("*.py")):
            functions.append({"name": fn_path.stem, "code": fn_path.read_text()})

    codegen.write_compiled_graph(graph_id, definition, functions)
