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


def create_agent(
    name: str,
    description: str,
    instructions: str,
    graph_model: str | None = None,
) -> str:
    """Create a new graph from user-provided name, description, and instructions.

    Steps: LLM produces JSON → we extract function bodies → write the generated
    Python module under <agents_path>/graphs/<id>/ → register in langgraph.json.

    `graph_model` is the model the GENERATED graph will call at runtime
    (independent of the CLI's active model used to build the JSON). Format:
    `"provider:model-id"`. If omitted, the generated module will read
    `DEFAULT_MODEL` from the server's environment at runtime.

    Returns a human-readable summary string.
    """
    from ..config import DEFAULT_MODELS, get_settings
    from ..llm import call_llm_simple
    from ..llm.prompts.builder import builder_system_prompt

    settings = get_settings()
    provider = state.active_model["provider"] or settings.default_provider
    model_id = state.active_model["model_id"] or settings.default_model or DEFAULT_MODELS.get(provider, "")

    graph_id = _name_to_id(name)

    user_prompt = (
        f"Create an agent with the following specifications:\n\n"
        f"Name: {name}\n"
        f"Description: {description}\n\n"
        f"Build instructions:\n{instructions}\n\n"
        f"Output the complete agent definition in a ```json code block."
    )

    state.console.print(f"[dim]Building graph '{name}' ({graph_id})...[/dim]")
    state.console.print(f"[dim]Using {model_display_name() or model_id}...[/dim]")

    result = asyncio.run(
        call_llm_simple(
            provider=provider,
            model_id=model_id,
            api_key=None,
            system=builder_system_prompt(),
            messages=[{"role": "user", "content": user_prompt}],
        )
    )

    definition = _extract_json_block(result["text"])
    if not definition:
        state.console.print("[bold red]Error:[/bold red] Could not parse agent definition from LLM response.")
        state.console.print("[dim]Raw response:[/dim]")
        state.console.print(result["text"][:2000])
        return "Agent creation failed — no valid JSON definition found."

    # Honor an explicit per-graph runtime model; clear the LLM's own choice
    # if the user opted for server-env-driven resolution.
    if graph_model:
        definition["model"] = graph_model
    else:
        definition.pop("model", None)

    functions = _extract_functions(definition)

    try:
        init_path = codegen.write_compiled_graph(graph_id, definition, functions)
    except (ValueError, NotImplementedError) as e:
        state.console.print(f"[bold red]Codegen error:[/bold red] {e}")
        return "Agent creation failed during codegen."

    registry.add_graph(graph_id)
    state.active_graph_id = graph_id

    summary = (
        f"Graph [bold]{graph_id}[/bold] generated at {init_path}\n"
        f"  Type: {definition.get('type', 'simple')}\n"
    )
    if definition.get("tools"):
        summary += f"  Tools: {', '.join(definition['tools'])}\n"
    if functions:
        summary += f"  Functions: {', '.join(f['name'] for f in functions)}\n"
    summary += f"  Tokens: {result['input_tokens']} ↑ / {result['output_tokens']} ↓\n"
    summary += "  [dim]Restart langosh-server to register the new graph.[/dim]"

    return summary
