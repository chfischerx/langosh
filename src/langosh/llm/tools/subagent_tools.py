"""Subagent tool — spawn a focused LLM agent with a restricted toolset.

A subagent is a recursive `call_with_tools` invocation with:
- A specialized system prompt (per role)
- A filtered subset of tools
- Its own conversation that ends when it returns a final answer

The subagent's nested tool calls are forwarded to the parent's on_event
with an indented prefix so they're visually distinct in the main stream.
"""

from __future__ import annotations

import threading
from typing import Any

import langosh.state as state

# Depth counter per-thread so recursive subagent calls don't run forever.
_local = threading.local()
_MAX_DEPTH = 2


def _depth() -> int:
    return getattr(_local, "depth", 0)


def _inc_depth() -> None:
    _local.depth = _depth() + 1


def _dec_depth() -> None:
    _local.depth = max(0, _depth() - 1)


# role -> (system_prompt, tool_name_filter)
_SUBAGENT_ROLES: dict[str, tuple[str, list[str]]] = {
    "researcher": (
        "You are a focused research assistant. Your job is to answer one specific "
        "question using the official LangChain/LangGraph/LangSmith documentation. "
        "Use `docs_search` first, then `docs_read` to fetch relevant pages. "
        "Return a concise, accurate answer citing the doc paths you consulted. "
        "Keep the answer short — the caller only wants the distilled facts.",
        ["docs_search", "docs_read"],
    ),
    "explorer": (
        "You are a read-only code explorer. Your job is to understand and summarize "
        "parts of a codebase without modifying anything. Use the file and git tools "
        "to read and search. Return a concise summary of what you found. Do not "
        "speculate about code you haven't read.",
        [
            "read_file", "list_directory", "glob_files", "grep_files",
            "git_status", "git_diff", "git_log", "git_show", "git_blame",
            "docs_search", "docs_read",
        ],
    ),
    "coder": (
        "You are a focused implementation assistant. Your job is to make a specific "
        "code change. Read relevant files first to understand the existing style, "
        "then make the change with `edit_file` or `write_file`. Return a short "
        "summary of what you did and which files you touched.",
        [
            "read_file", "list_directory", "glob_files", "grep_files",
            "git_status", "git_diff", "git_log", "git_show", "git_blame",
            "edit_file", "write_file",
            "docs_search", "docs_read",
        ],
    ),
}


SUBAGENT_TOOL = {
    "name": "spawn_subagent",
    "description": (
        "Spawn a focused subagent to handle a specific task with a restricted "
        "toolset. Use this to keep your main context clean when a task requires "
        "deep work that you don't need the full transcript of. "
        "Roles:\n"
        "  - researcher: docs-only; answers questions about LangChain/LangGraph APIs\n"
        "  - explorer: read-only code exploration; summarizes what code does\n"
        "  - coder: implements a focused change in a single area of the repo\n"
        "Pass a clear, self-contained task description — the subagent cannot "
        "see your conversation history."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "role": {
                "type": "string",
                "enum": list(_SUBAGENT_ROLES.keys()),
                "description": "Which subagent role to spawn.",
            },
            "task": {
                "type": "string",
                "description": "The task description for the subagent.",
            },
            "max_turns": {
                "type": "integer",
                "description": "Max tool-use turns for the subagent. Default 8.",
            },
        },
        "required": ["role", "task"],
    },
}


async def spawn_subagent(args: dict) -> str:
    """Execute a subagent call and return its final text."""
    role = args.get("role", "")
    task = args.get("task", "")
    max_turns = int(args.get("max_turns") or 8)

    if role not in _SUBAGENT_ROLES:
        return f"Error: unknown role '{role}'. Available: {', '.join(_SUBAGENT_ROLES)}"
    if not task.strip():
        return "Error: 'task' is required."

    if _depth() >= _MAX_DEPTH:
        return f"Error: subagent depth limit ({_MAX_DEPTH}) reached."

    system_prompt, tool_names = _SUBAGENT_ROLES[role]

    # Import here to avoid cycles with tools/__init__.py
    from .. import call_with_tools
    from . import ALL_TOOLS, make_guarded_dispatcher

    # Filter ALL_TOOLS by name (exclude spawn_subagent to prevent recursion loops
    # except via the depth counter which catches deeper nesting).
    filtered_tools = [t for t in ALL_TOOLS if t["name"] in tool_names]

    # Forward nested events with an indent prefix so the main stream shows them
    # as subagent activity.
    parent_on_event = getattr(_local, "on_event", None)
    indent = "  " * (_depth() + 1)

    async def _forward(event_type: str, data: dict) -> None:
        if parent_on_event is None:
            return
        if event_type == "token":
            # Skip token events from subagents — the spinner counter at the top
            # is already controlled by the parent call. Nested token floods
            # would be noisy.
            return
        if event_type == "tool_call":
            new_data = dict(data)
            new_data["name"] = f"{indent}\u2502  {data.get('name', '')}"
            await parent_on_event(event_type, new_data)
            return
        if event_type == "tool_result":
            new_data = dict(data)
            new_data["name"] = f"{indent}\u2502  {data.get('name', '')}"
            await parent_on_event(event_type, new_data)
            return
        if event_type == "status":
            await parent_on_event(event_type, data)
            return

    dispatcher = make_guarded_dispatcher("edit", state.console)

    # Pick a distinctive color per role so nested subagents visually differ.
    _ROLE_COLORS = {"researcher": "magenta", "explorer": "blue", "coder": "green"}
    color = _ROLE_COLORS.get(role, "cyan")
    task_preview = task if len(task) <= 200 else task[:197] + "..."

    _inc_depth()
    try:
        state.console.print(
            f"[bold {color}]{indent}\u250c\u2500 subagent spawned: "
            f"[{color}]{role}[/{color}][/bold {color}]"
        )
        state.console.print(
            f"[dim]{indent}\u2502  task: {task_preview}[/dim]"
        )
        result = await call_with_tools(
            provider=None,  # resolve from active model
            model_id=None,
            api_key=None,
            system=system_prompt,
            messages=[{"role": "user", "content": task}],
            tools=filtered_tools,
            tool_dispatcher=dispatcher,
            on_event=_forward,
            max_tool_turns=max_turns,
        )
        text = result.get("text", "").strip() or "(subagent returned no output)"
        # Closing line with a short preview of the return value.
        ret_preview = text if len(text) <= 200 else text[:197] + "..."
        state.console.print(
            f"[bold {color}]{indent}\u2514\u2500 subagent done: "
            f"[{color}]{role}[/{color}][/bold {color}] "
            f"[dim]\u2192 {ret_preview}[/dim]"
        )
        return text
    except Exception as e:
        state.console.print(
            f"[bold red]{indent}\u2514\u2500 subagent {role} failed:[/bold red] {e}"
        )
        return f"Error running subagent: {e}"
    finally:
        _dec_depth()


def set_parent_on_event(on_event: Any) -> None:
    """Called by the query layer so the tool can reach the parent's callback."""
    _local.on_event = on_event


TOOLS = [SUBAGENT_TOOL]
DISPATCH = {"spawn_subagent": spawn_subagent}
