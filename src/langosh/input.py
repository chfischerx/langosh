"""Prompt toolkit input widget with slash command completion."""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.containers import Float, FloatContainer, HSplit, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.layout.menus import CompletionsMenu
from prompt_toolkit.layout.processors import BeforeInput
from prompt_toolkit.styles import Style as PtStyle

import langosh.state as state

if TYPE_CHECKING:
    from .modes import ModeStack


class _DynamicCompleter(Completer):
    """Completer that queries the mode stack for current commands."""

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor.lstrip()
        if not text.startswith("/"):
            return
        prefix = text.lower()
        menu = _mode_stack.get_menu() if _mode_stack else []
        for cmd, desc in menu:
            if cmd.lower().startswith(prefix):
                yield Completion(
                    cmd,
                    start_position=-len(text),
                    display=cmd,
                    display_meta=desc,
                )


_history_path = os.path.join(os.path.expanduser("~"), ".langosh", "input_history")
_history = FileHistory(_history_path)

_style = PtStyle.from_dict({
    "separator": "fg:ansidarkgray",
    "mode-label": "bold fg:ansibrightcyan",
    "prompt": "bold fg:ansibrightcyan",
    "completion-menu": "bg:#1a1a2e fg:#8888aa",
    "completion-menu.completion.current": "bg:#e2e2e2 fg:#000000 bold",
    "completion-menu.meta.completion": "bg:#1a1a2e fg:#555577",
    "completion-menu.meta.completion.current": "bg:#e2e2e2 fg:#333333",
})


def model_display_name() -> str:
    """Get the display name of the active model, or fall back to model_id."""
    model_id = state.active_model["model_id"]
    if not model_id:
        return ""
    for mlist in state.model_cache.values():
        for m in mlist:
            if m.id == model_id:
                return m.name
    return model_id


# Global reference set by repl.py at startup.
_mode_stack: ModeStack | None = None


def set_mode_stack(stack: ModeStack) -> None:
    """Wire up the global mode stack reference for the input system."""
    global _mode_stack
    _mode_stack = stack


def _mode_bar() -> str:
    """Build the top separator with mode path and optional model name."""
    cols = os.get_terminal_size().columns
    path = _mode_stack.path if _mode_stack else "langosh"
    label = f" {path} "
    if _mode_stack and "llm" in path:
        name = model_display_name()
        if name:
            label = f" {path} ({name}) "
    pad = cols - len(label)
    left = pad // 2
    right = pad - left
    return "\u2500" * left + label + "\u2500" * right


_MENU_RESERVE = 14  # lines to reserve below input for completion dropdown


def get_input() -> str | None:
    """Prompt for one line of input with mode bar above and separator below.

    The widget stays in scrollback after submission — no erasing. This keeps
    the mode bar and user input visible as history.
    """
    # Reserve terminal space below for the completion dropdown
    sys.stdout.write("\n" * _MENU_RESERVE)
    sys.stdout.write(f"\033[{_MENU_RESERVE}A")
    sys.stdout.flush()

    sep = "\u2500" * os.get_terminal_size().columns
    completer = _DynamicCompleter()

    buf = Buffer(
        history=_history,
        completer=completer,
        complete_while_typing=True,
    )

    body = HSplit([
        Window(
            FormattedTextControl(lambda: [("class:separator", _mode_bar())]),
            height=1,
        ),
        Window(
            BufferControl(
                buffer=buf,
                input_processors=[BeforeInput("> ", style="class:prompt")],
            ),
            height=1,
        ),
        Window(FormattedTextControl(sep), height=1, style="class:separator"),
    ])

    layout = Layout(
        FloatContainer(
            content=body,
            floats=[
                Float(
                    xcursor=True,
                    ycursor=True,
                    transparent=True,
                    content=CompletionsMenu(max_height=16, scroll_offset=1),
                ),
            ],
        )
    )

    kb = KeyBindings()

    def _has_menu(b):
        return b.complete_state is not None

    @kb.add("up")
    def _up(event):
        if _has_menu(buf):
            buf.complete_previous()
        else:
            buf.history_backward()

    @kb.add("down")
    def _down(event):
        if _has_menu(buf):
            buf.complete_next()
        else:
            buf.history_forward()

    @kb.add("tab")
    def _tab(event):
        if _has_menu(buf):
            buf.complete_next()
        else:
            buf.start_completion()

    @kb.add("s-tab")
    def _shift_tab(event):
        if _has_menu(buf):
            buf.complete_previous()

    @kb.add("enter")
    def _accept(event):
        if _has_menu(buf):
            buf.complete_state = None
        text = buf.text
        if text.strip():
            buf.append_to_history()
        event.app.exit(result=text)

    @kb.add("escape")
    def _dismiss(event):
        if _has_menu(buf):
            buf.complete_state = None

    @kb.add("c-c")
    @kb.add("c-d")
    def _cancel(event):
        event.app.exit(result=None)

    prompt_app = Application(
        layout=layout,
        key_bindings=kb,
        style=_style,
        full_screen=False,
        erase_when_done=True,
    )
    result = prompt_app.run()
    _trim_history()
    return result


_MAX_HISTORY = 100


def _trim_history() -> None:
    """Keep only the last _MAX_HISTORY entries in the history file."""
    try:
        path = _history_path
        if not os.path.isfile(path):
            return
        with open(path) as f:
            lines = f.readlines()
        entries: list[list[str]] = []
        current: list[str] = []
        for line in lines:
            if line.startswith("#") and current:
                entries.append(current)
                current = []
            current.append(line)
        if current:
            entries.append(current)
        if len(entries) > _MAX_HISTORY:
            with open(path, "w") as f:
                f.writelines(line for entry in entries[-_MAX_HISTORY:] for line in entry)
    except OSError:
        pass
