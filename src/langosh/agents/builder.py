"""Agent builder — creates LangGraph agents from user instructions via LLM."""

import asyncio
import json
import re

import langosh.state as state

from ..input import model_display_name
from .store import create_agent_folder, name_to_id, save_definition, save_function, save_metadata


def _extract_json_block(text: str) -> dict | None:
    """Extract the first ```json code block from LLM response."""
    match = re.search(r"```json\s*\n(.*?)\n```", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def _extract_functions(definition: dict) -> list[tuple[str, str]]:
    """Extract function node code from a custom agent definition.

    Returns list of (name, code) tuples. Removes the code from the definition
    in-place (replaced with a reference).
    """
    functions = []
    nodes = definition.get("nodes", [])
    for node in nodes:
        if node.get("type") == "function" and "code" in node:
            name = node["name"]
            code = node.pop("code")
            node["code_file"] = f"functions/{name}.py"
            functions.append((name, code))
    return functions


def create_agent(name: str, description: str, instructions: str) -> str:
    """Create a new agent from user-provided name, description, and instructions.

    Calls the LLM to generate the agent definition, then saves all files.
    Returns a summary string.
    """
    from ..config import DEFAULT_MODELS, get_settings
    from ..llm import call_llm_simple
    from ..llm.prompts.builder import BUILDER_SYSTEM_PROMPT

    settings = get_settings()
    provider = state.active_model["provider"] or settings.default_provider
    model_id = state.active_model["model_id"] or settings.default_model or DEFAULT_MODELS.get(provider, "")

    agent_id = name_to_id(name)

    # Build the user prompt
    user_prompt = (
        f"Create an agent with the following specifications:\n\n"
        f"Name: {name}\n"
        f"Description: {description}\n\n"
        f"Build instructions:\n{instructions}\n\n"
        f"Output the complete agent definition in a ```json code block."
    )

    state.console.print(f"[dim]Building agent '{name}' ({agent_id})...[/dim]")
    state.console.print(f"[dim]Using {model_display_name() or model_id}...[/dim]")

    result = asyncio.run(
        call_llm_simple(
            provider=provider,
            model_id=model_id,
            api_key=None,
            system=BUILDER_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
    )

    # Parse the definition from the response
    definition = _extract_json_block(result["text"])
    if not definition:
        state.console.print("[bold red]Error:[/bold red] Could not parse agent definition from LLM response.")
        state.console.print("[dim]Raw response:[/dim]")
        state.console.print(result["text"][:2000])
        return "Agent creation failed — no valid JSON definition found."

    # Create folder structure
    create_agent_folder(agent_id)

    # Save metadata
    save_metadata(agent_id, name, description)

    # Extract and save functions
    functions = _extract_functions(definition)
    for func_name, func_code in functions:
        save_function(agent_id, func_name, func_code)

    # Save definition
    save_definition(agent_id, definition)

    # Save creation conversation as agent history
    from .editor import save_agent_history

    state.agent_messages.clear()
    state.agent_messages.extend([
        {"role": "user", "content": user_prompt},
        {"role": "assistant", "content": result["text"]},
    ])
    state.agent_summary = ""
    state.active_agent_id = agent_id
    save_agent_history(agent_id)

    # Summary
    agent_type = definition.get("type", "unknown")
    tools = definition.get("tools", [])
    nodes = definition.get("nodes", [])

    summary = f"Agent [bold]{name}[/bold] created in ./agents/{agent_id}/\n"
    summary += f"  Type: {agent_type}\n"
    if tools:
        summary += f"  Tools: {', '.join(tools)}\n"
    if nodes:
        summary += f"  Nodes: {len(nodes)}\n"
    if functions:
        summary += f"  Functions: {', '.join(n for n, _ in functions)}\n"
    summary += f"  Tokens: {result['input_tokens']} ↑ / {result['output_tokens']} ↓"

    return summary
