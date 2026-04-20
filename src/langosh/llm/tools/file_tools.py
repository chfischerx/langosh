"""File operation tools for LLM tool-calling."""

import asyncio
import glob as glob_mod
import os
import subprocess

_SENSITIVE_PATTERNS = {".env", "credentials", "secret", "token", ".pem", ".key"}

READ_FILE = {
    "name": "read_file",
    "description": "Read the contents of a file. Returns numbered lines.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path (absolute or relative)"},
            "offset": {"type": "integer", "description": "Start reading from this line number (1-based)"},
            "limit": {"type": "integer", "description": "Maximum number of lines to return (default 2000)"},
        },
        "required": ["path"],
    },
}

WRITE_FILE = {
    "name": "write_file",
    "description": "Write content to a file. Creates the file if it does not exist, overwrites if it does.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path to write to"},
            "content": {"type": "string", "description": "Content to write"},
        },
        "required": ["path", "content"],
    },
}

EDIT_FILE = {
    "name": "edit_file",
    "description": "Replace a specific string in a file. Fails if old_string is not found.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path to edit"},
            "old_string": {"type": "string", "description": "Exact string to find and replace"},
            "new_string": {"type": "string", "description": "Replacement string"},
        },
        "required": ["path", "old_string", "new_string"],
    },
}

LIST_DIRECTORY = {
    "name": "list_directory",
    "description": "List files and directories at a given path.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory path (default: current directory)"},
        },
        "required": [],
    },
}

GLOB_FILES = {
    "name": "glob_files",
    "description": "Find files matching a glob pattern (e.g. '**/*.py').",
    "input_schema": {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Glob pattern to match"},
            "path": {"type": "string", "description": "Base directory to search from (default: current directory)"},
        },
        "required": ["pattern"],
    },
}

GREP_FILES = {
    "name": "grep_files",
    "description": "Search file contents using a regex pattern. Returns matching lines with file paths and line numbers.",
    "input_schema": {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Regex pattern to search for"},
            "path": {"type": "string", "description": "File or directory to search in (default: current directory)"},
            "glob": {"type": "string", "description": "Glob to filter files (e.g. '*.py')"},
        },
        "required": ["pattern"],
    },
}


def _is_sensitive(path: str) -> bool:
    lower = path.lower()
    return any(p in lower for p in _SENSITIVE_PATTERNS)


async def read_file(args: dict) -> str:
    path = args["path"]
    offset = args.get("offset", 1)
    limit = args.get("limit", 2000)

    if not os.path.isfile(path):
        return f"Error: file not found: {path}"

    def _read():
        with open(path) as f:
            lines = f.readlines()
        start = max(0, offset - 1)
        selected = lines[start : start + limit]
        numbered = [f"{start + i + 1}\t{line.rstrip()}" for i, line in enumerate(selected)]
        result = "\n".join(numbered)
        if start + limit < len(lines):
            result += f"\n... ({len(lines) - start - limit} more lines)"
        return result

    return await asyncio.to_thread(_read)


async def write_file(args: dict) -> str:
    path = args["path"]
    content = args["content"]

    if _is_sensitive(path):
        return f"Error: refusing to write to sensitive path: {path}"

    def _write():
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        return f"Written {len(content)} bytes to {path}"

    return await asyncio.to_thread(_write)


async def edit_file(args: dict) -> str:
    path = args["path"]
    old_string = args["old_string"]
    new_string = args["new_string"]

    if not os.path.isfile(path):
        return f"Error: file not found: {path}"

    def _edit():
        with open(path) as f:
            content = f.read()
        count = content.count(old_string)
        if count == 0:
            return f"Error: old_string not found in {path}"
        if count > 1:
            return f"Error: old_string found {count} times in {path}. Provide more context to make it unique."
        new_content = content.replace(old_string, new_string, 1)
        with open(path, "w") as f:
            f.write(new_content)
        return f"Edited {path}: replaced 1 occurrence"

    return await asyncio.to_thread(_edit)


async def list_directory(args: dict) -> str:
    path = args.get("path", ".")

    if not os.path.isdir(path):
        return f"Error: directory not found: {path}"

    def _list():
        entries = sorted(os.listdir(path))
        lines = []
        for e in entries:
            full = os.path.join(path, e)
            suffix = "/" if os.path.isdir(full) else ""
            lines.append(f"{e}{suffix}")
        return "\n".join(lines) if lines else "(empty directory)"

    return await asyncio.to_thread(_list)


async def glob_files(args: dict) -> str:
    pattern = args["pattern"]
    path = args.get("path", ".")

    def _glob():
        full_pattern = os.path.join(path, pattern)
        matches = sorted(glob_mod.glob(full_pattern, recursive=True))
        if not matches:
            return f"No files matching: {pattern}"
        return "\n".join(matches[:500])

    return await asyncio.to_thread(_glob)


async def grep_files(args: dict) -> str:
    pattern = args["pattern"]
    path = args.get("path", ".")
    file_glob = args.get("glob", "")

    def _grep():
        cmd = ["grep", "-rn", "--color=never"]
        if file_glob:
            cmd.extend(["--include", file_glob])
        cmd.extend([pattern, path])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        output = result.stdout.strip()
        if not output:
            return f"No matches for pattern: {pattern}"
        lines = output.split("\n")
        if len(lines) > 200:
            return "\n".join(lines[:200]) + f"\n... ({len(lines) - 200} more matches)"
        return output

    return await asyncio.to_thread(_grep)


TOOLS = [READ_FILE, WRITE_FILE, EDIT_FILE, LIST_DIRECTORY, GLOB_FILES, GREP_FILES]
DISPATCH = {
    "read_file": read_file,
    "write_file": write_file,
    "edit_file": edit_file,
    "list_directory": list_directory,
    "glob_files": glob_files,
    "grep_files": grep_files,
}
