"""LLM tools for file operations and git."""

import asyncio
import os
import sys

from prompt_toolkit.application import Application
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.styles import Style as PtStyle

from .file_tools import DISPATCH as _FILE_DISPATCH
from .file_tools import TOOLS as _FILE_TOOLS
from .git_tools import DISPATCH as _GIT_DISPATCH
from .git_tools import TOOLS as _GIT_TOOLS
from .python_exec import DISPATCH as _PYTHON_DISPATCH
from .python_exec import TOOLS as _PYTHON_TOOLS

ALL_TOOLS: list[dict] = _FILE_TOOLS + _GIT_TOOLS + _PYTHON_TOOLS

_DISPATCH: dict = {**_FILE_DISPATCH, **_GIT_DISPATCH, **_PYTHON_DISPATCH}

READ_TOOLS = {"read_file", "list_directory", "glob_files", "grep_files",
              "git_status", "git_diff", "git_log", "git_show", "git_blame"}
WRITE_TOOLS = {"write_file", "edit_file", "execute_python"}

_APPROVAL_STYLE = PtStyle.from_dict({
    "separator": "fg:ansidarkgray",
    "option": "fg:ansiwhite",
    "option.selected": "bold fg:ansibrightcyan",
    "option.dim": "fg:ansidarkgray",
    "tool-name": "bold fg:ansiyellow",
})


async def dispatch_tool(name: str, args: dict) -> str:
    """Execute a tool by name and return its string result."""
    fn = _DISPATCH.get(name)
    if not fn:
        return f"Unknown tool: {name}"
    try:
        return await fn(args)
    except Exception as e:
        return f"Error executing {name}: {e}"


def _show_approval_widget(tool_name: str, args: dict, console) -> str:
    """Show an inline approval widget with arrow-key selection. Returns 'allow', 'deny', or 'always'."""

    # Print tool details above the widget
    path = args.get("path", "")
    label = f"{tool_name}" + (f": {path}" if path else "")
    console.print(f"\n[bold yellow]  → {label}[/bold yellow]")
    for k, v in args.items():
        val = str(v)
        if len(val) > 120:
            val = val[:120] + "..."
        console.print(f"[dim]    {k}: {val}[/dim]")

    # Count lines printed for tool details (label + args)
    detail_lines = 1 + len(args)

    options = [
        ("allow", f"Allow        {tool_name}"),
        ("deny", "Deny"),
        ("always", "Always allow  (this session)"),
    ]
    selected = [0]

    def _build_text():
        lines = []
        for i, (_, label) in enumerate(options):
            if i == selected[0]:
                lines.append(("class:option.selected", f"  ▸ {label}\n"))
            else:
                lines.append(("class:option.dim", f"    {label}\n"))
        return lines

    sep = "─" * os.get_terminal_size().columns

    layout = Layout(
        HSplit([
            Window(FormattedTextControl(sep), height=1, style="class:separator"),
            Window(FormattedTextControl(_build_text), height=len(options)),
            Window(FormattedTextControl(sep), height=1, style="class:separator"),
        ])
    )

    kb = KeyBindings()

    @kb.add("up")
    def _up(event):
        selected[0] = (selected[0] - 1) % len(options)

    @kb.add("down")
    def _down(event):
        selected[0] = (selected[0] + 1) % len(options)

    @kb.add("enter")
    def _accept(event):
        event.app.exit(result=options[selected[0]][0])

    @kb.add("c-c")
    def _cancel(event):
        event.app.exit(result="deny")

    widget_app = Application(
        layout=layout,
        key_bindings=kb,
        style=_APPROVAL_STYLE,
        full_screen=False,
    )
    result = widget_app.run()

    # Erase the widget (2 separators + option lines) and the detail lines
    erase_count = 2 + len(options) + detail_lines
    sys.stdout.write(f"\033[{erase_count}A\033[J")
    sys.stdout.flush()

    return result


def make_guarded_dispatcher(sub_mode: str, console):
    """Create a tool dispatcher that enforces approval based on sub-mode.

    Sub-modes:
      plan — ask for approval on every tool call
      auto — auto-approve reads, ask for writes
      edit — auto-approve everything
    """
    # Track tools that have been "always allowed" this session
    always_allowed: set[str] = set()

    def _needs_approval(tool_name: str) -> bool:
        if sub_mode == "edit":
            return False
        if tool_name in always_allowed:
            return False
        if sub_mode == "plan":
            return True
        # auto: only writes need approval
        return tool_name in WRITE_TOOLS

    async def _ask_approval(name: str, args: dict) -> str:
        return await asyncio.to_thread(_show_approval_widget, name, args, console)

    async def guarded_dispatch(name: str, args: dict) -> str:
        if _needs_approval(name):
            choice = await _ask_approval(name, args)
            if choice == "deny":
                console.print(f"[dim]  ✗ {name} denied[/dim]")
                return "Tool call denied by user."
            if choice == "always":
                always_allowed.add(name)
            console.print(f"[dim]  ✓ {name} approved[/dim]")
        return await dispatch_tool(name, args)

    return guarded_dispatch
