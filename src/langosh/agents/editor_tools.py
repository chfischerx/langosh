"""Builder tools for editing agent definitions and functions."""

import asyncio
import json
import os
from pathlib import Path

from .store import AGENTS_DIR

# --- Tool schemas (Anthropic format) ---

READ_DEFINITION = {
    "name": "read_definition",
    "description": "Read the full agent definition JSON.",
    "input_schema": {"type": "object", "properties": {}, "required": []},
}

EDIT_DEFINITION = {
    "name": "edit_definition",
    "description": "Apply a string replacement to definition.json. Fails if old_str is not found or matches multiple times.",
    "input_schema": {
        "type": "object",
        "properties": {
            "old_str": {"type": "string", "description": "Exact string to find in definition.json"},
            "new_str": {"type": "string", "description": "Replacement string"},
        },
        "required": ["old_str", "new_str"],
    },
}

UPDATE_DEFINITION = {
    "name": "update_definition",
    "description": "Partially update the agent definition by merging a patch dict. Only include fields you want to change.",
    "input_schema": {
        "type": "object",
        "properties": {
            "patch": {"type": "object", "description": "Dict of fields to merge into the definition"},
        },
        "required": ["patch"],
    },
}

LIST_FUNCTIONS = {
    "name": "list_functions",
    "description": "List the names of all function files stored for this agent.",
    "input_schema": {"type": "object", "properties": {}, "required": []},
}

READ_FUNCTION = {
    "name": "read_function",
    "description": "Read the source code of one function file by name (without .py extension).",
    "input_schema": {
        "type": "object",
        "properties": {"name": {"type": "string", "description": "Function name (without .py)"}},
        "required": ["name"],
    },
}

WRITE_FUNCTION = {
    "name": "write_function",
    "description": "Write or rewrite a function file. Use for new functions or full rewrites.",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Function name (without .py)"},
            "code": {"type": "string", "description": "Complete Python source code"},
        },
        "required": ["name", "code"],
    },
}

EDIT_FUNCTION = {
    "name": "edit_function",
    "description": "Apply a string replacement to a function file. Fails if old_str is not found or matches multiple times.",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Function name (without .py)"},
            "old_str": {"type": "string", "description": "Exact string to find"},
            "new_str": {"type": "string", "description": "Replacement string"},
        },
        "required": ["name", "old_str", "new_str"],
    },
}

TOOLS = [READ_DEFINITION, EDIT_DEFINITION, UPDATE_DEFINITION, LIST_FUNCTIONS, READ_FUNCTION, WRITE_FUNCTION, EDIT_FUNCTION]

# Read-only vs write tools for approval control
READ_TOOLS = {"read_definition", "list_functions", "read_function"}
WRITE_TOOLS = {"edit_definition", "update_definition", "write_function", "edit_function"}


# --- Tool implementations ---

def _def_path(agent_id: str) -> str:
    return os.path.join(AGENTS_DIR, agent_id, "definition.json")


def _func_path(agent_id: str, name: str) -> str:
    return os.path.join(AGENTS_DIR, agent_id, "functions", f"{name}.py")


def make_editor_dispatch(agent_id: str):
    """Create a dispatch dict bound to a specific agent."""

    async def read_definition(args: dict) -> str:
        path = _def_path(agent_id)
        if not os.path.isfile(path):
            return "Error: no definition.json found"
        return await asyncio.to_thread(Path(path).read_text)

    async def edit_definition(args: dict) -> str:
        path = _def_path(agent_id)
        old_str = args["old_str"]
        new_str = args["new_str"]

        def _edit():
            content = Path(path).read_text()
            count = content.count(old_str)
            if count == 0:
                return "Error: old_str not found in definition.json"
            if count > 1:
                return f"Error: old_str found {count} times. Provide more context."
            Path(path).write_text(content.replace(old_str, new_str, 1))
            return "definition.json updated"

        return await asyncio.to_thread(_edit)

    async def update_definition(args: dict) -> str:
        path = _def_path(agent_id)
        patch = args["patch"]

        def _update():
            with open(path) as f:
                definition = json.load(f)
            definition.update(patch)
            with open(path, "w") as f:
                json.dump(definition, f, indent=2, ensure_ascii=False)
            return f"definition.json updated: {', '.join(patch.keys())}"

        return await asyncio.to_thread(_update)

    async def list_functions(args: dict) -> str:
        func_dir = os.path.join(AGENTS_DIR, agent_id, "functions")
        if not os.path.isdir(func_dir):
            return "No functions directory"
        files = sorted(f[:-3] for f in os.listdir(func_dir) if f.endswith(".py"))
        return "\n".join(files) if files else "No function files"

    async def read_function(args: dict) -> str:
        path = _func_path(agent_id, args["name"])
        if not os.path.isfile(path):
            return f"Error: function '{args['name']}' not found"
        return await asyncio.to_thread(Path(path).read_text)

    async def write_function(args: dict) -> str:
        path = _func_path(agent_id, args["name"])
        os.makedirs(os.path.dirname(path), exist_ok=True)

        def _write():
            Path(path).write_text(args["code"])
            return f"Function '{args['name']}' written"

        return await asyncio.to_thread(_write)

    async def edit_function(args: dict) -> str:
        path = _func_path(agent_id, args["name"])
        old_str = args["old_str"]
        new_str = args["new_str"]

        def _edit():
            if not os.path.isfile(path):
                return f"Error: function '{args['name']}' not found"
            content = Path(path).read_text()
            count = content.count(old_str)
            if count == 0:
                return "Error: old_str not found"
            if count > 1:
                return f"Error: old_str found {count} times"
            Path(path).write_text(content.replace(old_str, new_str, 1))
            return f"Function '{args['name']}' updated"

        return await asyncio.to_thread(_edit)

    return {
        "read_definition": read_definition,
        "edit_definition": edit_definition,
        "update_definition": update_definition,
        "list_functions": list_functions,
        "read_function": read_function,
        "write_function": write_function,
        "edit_function": edit_function,
    }
