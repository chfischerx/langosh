"""Git tools for LLM tool-calling (read-only operations)."""

import asyncio
import subprocess


def _run_git(*args: str, timeout: int = 30) -> str:
    """Run a git command and return its output."""
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        return f"Error: {result.stderr.strip()}"
    return result.stdout.strip() or "(no output)"


GIT_STATUS = {
    "name": "git_status",
    "description": "Show the working tree status (modified, staged, untracked files).",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}

GIT_DIFF = {
    "name": "git_diff",
    "description": "Show changes in the working tree or staged changes.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Limit diff to a specific file or directory"},
            "staged": {"type": "boolean", "description": "Show staged changes only (default: false)"},
        },
        "required": [],
    },
}

GIT_LOG = {
    "name": "git_log",
    "description": "Show recent commit history.",
    "input_schema": {
        "type": "object",
        "properties": {
            "count": {"type": "integer", "description": "Number of commits to show (default: 10)"},
            "path": {"type": "string", "description": "Limit to commits touching this path"},
        },
        "required": [],
    },
}

GIT_SHOW = {
    "name": "git_show",
    "description": "Show details of a specific commit (message, diff).",
    "input_schema": {
        "type": "object",
        "properties": {
            "ref": {"type": "string", "description": "Commit hash, branch, or tag (default: HEAD)"},
        },
        "required": [],
    },
}

GIT_BLAME = {
    "name": "git_blame",
    "description": "Show line-by-line blame annotation for a file.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path to blame"},
        },
        "required": ["path"],
    },
}


async def git_status(args: dict) -> str:
    return await asyncio.to_thread(_run_git, "status", "--short")


async def git_diff(args: dict) -> str:
    cmd = ["diff"]
    if args.get("staged"):
        cmd.append("--cached")
    path = args.get("path")
    if path:
        cmd.extend(["--", path])
    return await asyncio.to_thread(_run_git, *cmd)


async def git_log(args: dict) -> str:
    count = str(args.get("count", 10))
    cmd = ["log", f"--max-count={count}", "--oneline"]
    path = args.get("path")
    if path:
        cmd.extend(["--", path])
    return await asyncio.to_thread(_run_git, *cmd)


async def git_show(args: dict) -> str:
    ref = args.get("ref", "HEAD")
    return await asyncio.to_thread(_run_git, "show", "--stat", ref)


async def git_blame(args: dict) -> str:
    path = args["path"]
    return await asyncio.to_thread(_run_git, "blame", "--no-color", path)


TOOLS = [GIT_STATUS, GIT_DIFF, GIT_LOG, GIT_SHOW, GIT_BLAME]
DISPATCH = {
    "git_status": git_status,
    "git_diff": git_diff,
    "git_log": git_log,
    "git_show": git_show,
    "git_blame": git_blame,
}
