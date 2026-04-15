"""File operation tools for LangGraph agents — typed wrappers around LLM tools."""

from ...llm.tools.file_tools import (
    edit_file as _edit_file,
    glob_files as _glob_files,
    grep_files as _grep_files,
    list_directory as _list_directory,
    read_file as _read_file,
    write_file as _write_file,
)


async def read_file(path: str, offset: int = 1, limit: int = 2000) -> str:
    """Read the contents of a file. Returns numbered lines.

    Args:
        path: File path (absolute or relative)
        offset: Start reading from this line number (1-based)
        limit: Maximum number of lines to return
    """
    return await _read_file({"path": path, "offset": offset, "limit": limit})


async def write_file(path: str, content: str) -> str:
    """Write content to a file. Creates the file if it does not exist, overwrites if it does.

    Args:
        path: File path to write to
        content: Content to write
    """
    return await _write_file({"path": path, "content": content})


async def edit_file(path: str, old_string: str, new_string: str) -> str:
    """Replace a specific string in a file. Fails if old_string is not found.

    Args:
        path: File path to edit
        old_string: Exact string to find and replace
        new_string: Replacement string
    """
    return await _edit_file({"path": path, "old_string": old_string, "new_string": new_string})


async def list_directory(path: str = ".") -> str:
    """List files and directories at a given path.

    Args:
        path: Directory path (default: current directory)
    """
    return await _list_directory({"path": path})


async def glob_files(pattern: str, path: str = ".") -> str:
    """Find files matching a glob pattern (e.g. '**/*.py').

    Args:
        pattern: Glob pattern to match
        path: Base directory to search from
    """
    return await _glob_files({"pattern": pattern, "path": path})


async def grep_files(pattern: str, path: str = ".", glob: str = "") -> str:
    """Search file contents using a regex pattern.

    Args:
        pattern: Regex pattern to search for
        path: File or directory to search in
        glob: Glob to filter files (e.g. '*.py')
    """
    args: dict = {"pattern": pattern, "path": path}
    if glob:
        args["glob"] = glob
    return await _grep_files(args)
