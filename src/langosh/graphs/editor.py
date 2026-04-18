"""Agent editor — LLM conversation for modifying graphs via builder tools."""

import asyncio
import time

import langosh.state as state

from ..context import apply_window
from ..input import model_display_name
from ..rendering import print_renderables, render_semantic
from . import codegen, registry
from .editor_tools import TOOLS, WRITE_TOOLS, make_editor_dispatch


def _make_guarded_dispatcher(graph_id: str):
    """Create a guarded dispatcher for editor tools respecting agent_sub_mode."""
    dispatch = make_editor_dispatch(graph_id)

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

    start = time.monotonic()
    try:
        async def _on_event(event_type: str, data: dict) -> None:
            name = data.get("name", "")
            if event_type == "tool_call":
                state.console.print(f"[dim]  ↳ calling {name}...[/dim]")
            elif event_type == "tool_result":
                state.console.print(f"[dim]  ↳ {name} done[/dim]")

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
