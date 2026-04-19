"""Agent builder — LLM produces a JSON definition; we generate Python and register it."""

import asyncio
import json
import re

import langosh.state as state

from ..input import model_display_name
from . import codegen, registry


def _name_to_id(name: str) -> str:
    """Convert a display name to a folder-safe graph_id."""
    gid = name.lower().strip()
    gid = re.sub(r"[^\w\s-]", "", gid)
    gid = re.sub(r"[\s-]+", "_", gid)
    return gid


def _extract_json_block(text: str) -> dict | None:
    """Extract the first ```json code block from an LLM response."""
    match = re.search(r"```json\s*\n(.*?)\n```", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def _extract_functions(definition: dict) -> list[dict]:
    """Extract function-node code into separate {"name", "code"} entries.

    Edits the definition in-place: each function node loses its `code` field
    and gains a `code_file` reference.
    """
    functions: list[dict] = []
    for node in definition.get("nodes", []):
        if node.get("type") == "function" and "code" in node:
            name = node["name"]
            code = node.pop("code")
            node["code_file"] = f"functions/{name}.py"
            functions.append({"name": name, "code": code})
    return functions


def start_create(
    name: str,
    description: str,
    instructions: str,
    graph_model: str | None = None,
) -> None:
    """Seed `state.pending_create` with the builder conversation context.

    `graph_model` is the model the GENERATED graph will call at runtime
    (independent of the CLI's active model used to build the JSON). Format:
    `"provider:model-id"`. If omitted, the generated module will read
    `DEFAULT_MODEL` from the server's environment at runtime.

    Does NOT make the LLM call — the caller is expected to start one via
    `run_in_background("...", builder_turn)` so the input widget stays live.
    """
    from ..config import DEFAULT_MODELS, get_settings
    from ..llm.prompts.builder import builder_system_prompt

    settings = get_settings()
    provider = state.active_model["provider"] or settings.default_provider
    model_id = state.active_model["model_id"] or settings.default_model or DEFAULT_MODELS.get(provider, "")

    graph_id = _name_to_id(name)

    model_line = (
        f"Runtime model: already chosen by the user — {graph_model!r}. "
        "Do NOT ask the user about the model."
    ) if graph_model else (
        "Runtime model: already chosen by the user — the server's "
        "DEFAULT_MODEL env var controls it. Do NOT ask the user about the "
        "model, and do NOT set a `model` field in the definition."
    )

    seed = (
        f"Create an agent with the following specifications:\n\n"
        f"Name: {name}\n"
        f"Description: {description}\n\n"
        f"Build instructions:\n{instructions}\n\n"
        f"{model_line}\n\n"
        f"BEFORE emitting any ```json block, scan the build instructions for "
        f"tool categories mentioned without a specific tool name — e.g. "
        f"\"web search\", \"send email\", \"query a database\", \"post to "
        f"Slack\", \"read files\". For each such category:\n"
        f"  - Look up the matching tools in the catalog (with their source "
        f"tag + any API-key requirement).\n"
        f"  - Ask the user which one to use, offering a concrete default "
        f"(prefer no-API-key options).\n"
        f"Also ask about any topology ambiguity (simple ReAct vs custom "
        f"multi-node pipeline) when it isn't obvious from the ask.\n\n"
        f"Only after the user answers (or says \"use defaults\") do you "
        f"emit the definition. If there genuinely is nothing to clarify "
        f"(e.g. the user named every tool + topology explicitly), you may "
        f"proceed directly."
    )

    state.pending_create = {
        "name": name,
        "description": description,
        "graph_id": graph_id,
        "graph_model": graph_model,
        "provider": provider,
        "model_id": model_id,
        "system_prompt": builder_system_prompt(),
        "messages": [{"role": "user", "content": seed}],
        "total_in": 0,
        "total_out": 0,
    }
    state.console.print(
        f"[dim]Building graph '{name}' ({graph_id})... "
        "(builder may ask clarifying questions; /cancel to abort)[/dim]"
    )


def builder_turn() -> None:
    """Run one turn of the builder conversation. Must be called from a worker
    thread (i.e. via `run_in_background`) so the REPL input widget stays live
    while the LLM responds.

    Appends the LLM reply to `state.pending_create["messages"]`. If the reply
    contains a ```json definition, finalizes the graph and clears
    `state.pending_create`. Otherwise prints the reply; the next user input
    will become the next user turn."""
    from ..input import model_display_name, set_processing
    from ..llm import call_with_tools
    from ..llm.tools.docs_tools import DISPATCH as _DOCS_DISPATCH
    from ..llm.tools.docs_tools import TOOLS as _DOCS_TOOLS
    from ..llm.tools.subagent_tools import DISPATCH as _SUBAGENT_DISPATCH
    from ..llm.tools.subagent_tools import TOOLS as _SUBAGENT_TOOLS
    from ..llm.tools.subagent_tools import set_parent_on_event
    from ..queries import _format_tool_args
    from ..rendering import print_renderables, render_semantic

    pc = state.pending_create
    if pc is None:
        return

    tools = _DOCS_TOOLS + _SUBAGENT_TOOLS
    dispatch = {**_DOCS_DISPATCH, **_SUBAGENT_DISPATCH}

    async def _dispatch(name: str, args: dict) -> str:
        fn = dispatch.get(name)
        if not fn:
            return f"Unknown tool: {name}"
        try:
            return await fn(args)
        except Exception as e:
            return f"Error executing {name}: {e}"

    stream = {"buf": "", "n": 0}
    base_msg = f"Calling {model_display_name() or pc['model_id']}"

    def _preview(buf: str) -> str:
        # Last ~60 chars, newlines collapsed, stripped of a bit of XML noise
        # so the tail shows something readable while streaming.
        tail = buf[-80:].replace("\n", " ").replace("\t", " ")
        tail = " ".join(tail.split())
        if len(tail) > 60:
            tail = "…" + tail[-60:]
        return tail

    async def _on_event(event_type: str, data: dict) -> None:
        name = data.get("name", "")
        if event_type == "token":
            chunk = data.get("text", "")
            if chunk:
                stream["buf"] += chunk
                stream["n"] += len(chunk)
                preview = _preview(stream["buf"])
                if preview:
                    set_processing(f"{base_msg} · {preview}")
                else:
                    set_processing(f"{base_msg} ({stream['n']} chars)")
        elif event_type == "status":
            text = data.get("text", "").strip()
            if text:
                state.console.print(f"[dim italic]  • {text}[/dim italic]")
        elif event_type == "tool_call":
            args_str = _format_tool_args(data.get("input", {}))
            state.console.print(f"[dim]  ↳ {name}([/dim][cyan]{args_str}[/cyan][dim])[/dim]")
            # Reset the streaming tail so it doesn't drag in tool-arg text.
            stream["buf"] = ""
        elif event_type == "tool_result":
            state.console.print(f"[dim]  ↳ {name} done[/dim]")

    set_parent_on_event(_on_event)

    result = asyncio.run(
        call_with_tools(
            provider=pc["provider"],
            model_id=pc["model_id"],
            api_key=None,
            system=pc["system_prompt"],
            messages=pc["messages"],
            tools=tools,
            tool_dispatcher=_dispatch,
            on_event=_on_event,
        )
    )
    pc["total_in"] += result.get("input_tokens", 0)
    pc["total_out"] += result.get("output_tokens", 0)
    reply = result["text"]
    pc["messages"].append({"role": "assistant", "content": reply})

    definition = _extract_json_block(reply)
    if definition is None:
        print_renderables(state.console, render_semantic(reply))
        state.console.print(
            "[dim]Reply below to continue, or /cancel to abort.[/dim]"
        )
        return

    _finalize_create(definition, pc)


def continue_create(text: str) -> None:
    """Append a user reply to the builder conversation and run the next turn.
    Must be called from a worker thread (via `run_in_background`)."""
    pc = state.pending_create
    if pc is None:
        return
    pc["messages"].append({"role": "user", "content": text})
    builder_turn()


def _finalize_create(definition: dict, pc: dict) -> None:
    """Write the generated module, register it, print the summary, and clear
    pending state."""
    graph_id = pc["graph_id"]
    graph_model = pc["graph_model"]

    if graph_model:
        definition["model"] = graph_model
    else:
        definition.pop("model", None)

    functions = _extract_functions(definition)

    try:
        init_path = codegen.write_compiled_graph(graph_id, definition, functions)
    except (ValueError, NotImplementedError) as e:
        state.console.print(f"[bold red]Codegen error:[/bold red] {e}")
        state.console.print("[yellow]Agent creation failed during codegen.[/yellow]")
        state.pending_create = None
        return

    registry.add_graph(graph_id)
    state.active_graph_id = graph_id

    # Build a rich summary of what was generated.
    gtype = definition.get("type", "simple")
    lines: list[str] = [
        f"[green]✓ Graph [bold]{graph_id}[/bold] created.[/green]",
        f"  [dim]Type:[/dim] {gtype}",
        f"  [dim]Path:[/dim] {init_path}",
    ]

    # Tool references — from the top-level `tools` (simple agents) plus any
    # referenced inside tool/llm nodes (custom agents).
    tool_names: set[str] = set(definition.get("tools", []) or [])
    for node in definition.get("nodes", []) or []:
        if node.get("type") == "tool" and node.get("tool"):
            tool_names.add(node["tool"])
        if node.get("type") == "llm":
            for t in node.get("tools", []) or []:
                tool_names.add(t)
    if tool_names:
        lines.append(f"  [dim]Tools:[/dim] {', '.join(sorted(tool_names))}")

    if gtype == "custom":
        state_fields = list((definition.get("state") or {}).keys())
        nodes = definition.get("nodes") or []
        edges = definition.get("edges") or []
        if state_fields:
            lines.append(f"  [dim]State:[/dim] {', '.join(state_fields)}")
        if nodes:
            node_summary = ", ".join(f"{n.get('name','?')}({n.get('type','?')})" for n in nodes)
            lines.append(f"  [dim]Nodes ({len(nodes)}):[/dim] {node_summary}")
        if edges:
            lines.append(f"  [dim]Edges:[/dim] {len(edges)}")

    context = definition.get("context") or {}
    if context:
        lines.append(f"  [dim]Context:[/dim] {', '.join(context.keys())}")

    if functions:
        lines.append(f"  [dim]Functions:[/dim] {', '.join(f['name'] for f in functions)}")

    # API-key hints — if any selected tool is known to need one.
    _API_KEY_HINTS = {
        "tavily_search": "TAVILY_API_KEY",
        "brave_search": "BRAVE_SEARCH_API_KEY",
        "bing_search": "BING_SUBSCRIPTION_KEY",
        "bing_search_results_json": "BING_SUBSCRIPTION_KEY",
        "google_search": "GOOGLE_API_KEY + GOOGLE_CSE_ID",
        "google_search_results_json": "GOOGLE_API_KEY + GOOGLE_CSE_ID",
        "google_serper": "SERPER_API_KEY",
        "google_serper_results_json": "SERPER_API_KEY",
    }
    keys_needed = sorted({v for n, v in _API_KEY_HINTS.items() if n in tool_names})
    if keys_needed:
        lines.append(f"  [yellow]Server env vars:[/yellow] {', '.join(keys_needed)}")

    lines.append(f"  [dim]Tokens: {pc['total_in']} ↑ / {pc['total_out']} ↓[/dim]")
    lines.append(
        "  [dim]Next: /select "
        + graph_id
        + " to edit · /compile to rebuild · /deploy to push[/dim]"
    )

    state.pending_create = None
    state.console.print("")
    for line in lines:
        state.console.print(line)
