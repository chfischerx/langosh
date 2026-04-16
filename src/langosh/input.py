"""Prompt toolkit input widget with slash command completion."""

import os
import sys

from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.containers import Float, FloatContainer, HSplit, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.layout.menus import CompletionsMenu
from prompt_toolkit.layout.processors import BeforeInput
from prompt_toolkit.styles import Style as PtStyle

from .commands.menus import ADMIN_COMMANDS_MENU, AGENT_EDIT_COMMANDS_MENU, AGENTS_COMMANDS_MENU, AGENTS_GRAPH_COMMANDS_MENU, CHAT_COMMANDS_MENU, CODE_COMMANDS_MENU
import langosh.state as state


class SlashCompleter(Completer):
    """Completer that only activates when input starts with '/'."""

    def __init__(self, commands: list[tuple[str, str]]) -> None:
        self.commands = commands

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor.lstrip()
        if not text.startswith("/"):
            return
        prefix = text.lower()
        for cmd, desc in self.commands:
            if cmd.lower().startswith(prefix):
                yield Completion(
                    cmd,
                    start_position=-len(text),
                    display=cmd,
                    display_meta=desc,
                )


_chat_completer = SlashCompleter(CHAT_COMMANDS_MENU)
_code_completer = SlashCompleter(CODE_COMMANDS_MENU)
_agents_completer = SlashCompleter(AGENTS_COMMANDS_MENU)
_agents_graph_completer = SlashCompleter(AGENTS_GRAPH_COMMANDS_MENU)
_agent_edit_completer = SlashCompleter(AGENT_EDIT_COMMANDS_MENU)
_admin_completer = SlashCompleter(ADMIN_COMMANDS_MENU)

_history = InMemoryHistory()

_style = PtStyle.from_dict({
    "separator": "fg:ansidarkgray",
    "mode-label": "bold fg:ansibrightcyan",
    "prompt": "bold fg:ansibrightcyan",
    "completion-menu": "bg:ansibrightblack fg:ansiwhite",
    "completion-menu.completion.current": "bg:ansibrightcyan fg:ansiblack",
    "completion-menu.meta.completion": "bg:ansibrightblack fg:ansidarkgray",
    "completion-menu.meta.completion.current": "bg:ansibrightcyan fg:ansiblack",
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


def _mode_bar() -> str:
    """Build the top separator with mode label and active model name."""
    cols = os.get_terminal_size().columns
    if state.current_mode == "code":
        mode_label = f"code:{state.code_sub_mode}"
    elif state.current_mode == "main" and state.agent_editing:
        mode_label = f"{state.active_graph_id}:edit:{state.agent_sub_mode}"
    elif state.current_mode == "main" and state.active_graph_id:
        mode_label = state.active_graph_id
    elif state.current_mode == "main":
        mode_label = "langosh"
    else:
        mode_label = state.current_mode
    label = f" {mode_label} "
    if state.current_mode in ("chat", "code") and state.active_model["provider"]:
        name = model_display_name()
        if name:
            label = f" {mode_label} ({name}) "
    pad = cols - len(label)
    left = pad // 2
    right = pad - left
    return "─" * left + label + "─" * right


_MENU_RESERVE = 14  # lines to reserve below input for completion dropdown


def get_input() -> str | None:
    """Prompt for one line of input with separator lines above and below."""
    # Reserve terminal space below for the completion dropdown
    sys.stdout.write("\n" * _MENU_RESERVE)
    sys.stdout.write(f"\033[{_MENU_RESERVE}A")
    sys.stdout.flush()

    sep = "─" * os.get_terminal_size().columns
    effective_mode = "agent_edit" if state.current_mode == "main" and state.agent_editing else state.current_mode
    _completers = {"chat": _chat_completer, "code": _code_completer, "agent_edit": _agent_edit_completer, "admin": _admin_completer}
    if effective_mode == "main":
        completer = _agents_graph_completer if state.active_graph_id else _agents_completer
    else:
        completer = _completers.get(effective_mode, _agents_completer)

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

    @kb.add("enter")
    def _accept(event):
        text = buf.text
        if text.strip():
            _history.store_string(text)
        event.app.exit(result=text)

    @kb.add("c-c")
    @kb.add("c-d")
    def _cancel(event):
        event.app.exit(result=None)

    prompt_app = Application(
        layout=layout,
        key_bindings=kb,
        style=_style,
        full_screen=False,
    )
    return prompt_app.run()


def erase_lines(n: int) -> None:
    """Erase the last n lines from the terminal."""
    sys.stdout.write(f"\033[{n}A\033[J")
    sys.stdout.flush()
