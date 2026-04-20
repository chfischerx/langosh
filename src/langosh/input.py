"""Prompt toolkit input widget with slash command completion."""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.filters import Condition
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout.containers import ConditionalContainer, Float, FloatContainer, HSplit, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
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
    "spinner": "fg:ansicyan",
    "status": "fg:ansidarkgray",
    "ctrlc-hint": "fg:ansiyellow",
    "submode-plan": "fg:ansiyellow",
    "submode-auto": "fg:ansicyan",
    "submode-edit": "fg:ansimagenta",
    "submode-hint": "fg:ansidarkgray",
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


def get_mode_stack() -> "ModeStack | None":
    """Access the global mode stack. Used by background workers (e.g. the
    builder) that need to push a mode after an async task completes."""
    return _mode_stack


# ── Bracketed-paste abbreviation ─────────────────────────────────────
# Pastes longer than PASTE_ABBREV_THRESHOLD chars are replaced in the
# buffer with a short placeholder like `[Pasted #1, 42 lines]` or
# `[Pasted #1, 820 chars]`; the raw content is kept in the store below
# and inlined again before `get_input()` returns, so downstream command
# / LLM handlers see the full content while the widget and the
# scrollback echo stay readable.
PASTE_ABBREV_THRESHOLD = 500
_paste_store: dict[str, str] = {}
_paste_counter: int = 0
_PLACEHOLDER_RE = re.compile(r"\[Pasted #\d+, \d+ (?:lines|chars)\]")


def _stash_paste(content: str) -> str:
    global _paste_counter
    _paste_counter += 1
    if "\n" in content:
        label = f"{content.count(chr(10)) + 1} lines"
    else:
        label = f"{len(content)} chars"
    token = f"[Pasted #{_paste_counter}, {label}]"
    _paste_store[token] = content
    return token


def expand_pastes(text: str) -> str:
    """Expand `[Pasted #N, K lines]` placeholders back to their full
    stored content. Placeholders with no known backing content
    (e.g. recalled from history in a later session) are left intact,
    which is the safer default — the user sees exactly what they
    recalled."""
    if not _paste_store:
        return text
    return _PLACEHOLDER_RE.sub(lambda m: _paste_store.get(m.group(0), m.group(0)), text)


_SPINNER_FRAMES = "\u280b\u2819\u2839\u2838\u283c\u2834\u2826\u2827\u2807\u280f"
_processing_message: str | None = None
_last_ctrlc: float = 0.0  # timestamp of last Ctrl+C press
_CTRLC_WINDOW = 1.0  # seconds


def set_processing(message: str | None) -> None:
    """Show/hide a spinner line above the mode bar. Thread-safe."""
    global _processing_message
    _processing_message = message


def _ctrlc_active() -> bool:
    """True if a Ctrl+C was pressed within the confirmation window."""
    import time as _time
    return _last_ctrlc > 0 and _time.monotonic() - _last_ctrlc < _CTRLC_WINDOW


def _status_line() -> list[tuple[str, str]]:
    """Format the spinner line (shown only when processing)."""
    import time as _time
    if not _processing_message:
        return [("", "")]
    frame = _SPINNER_FRAMES[int(_time.monotonic() * 10) % len(_SPINNER_FRAMES)]
    return [("class:spinner", f"{frame} "), ("class:status", _processing_message)]


def _sub_mode_name() -> str | None:
    """Return the current mode's sub-mode name, if any."""
    if _mode_stack is None:
        return None
    return _mode_stack.current.get_sub_mode()


_SUB_MODE_ICONS = {
    "plan": "\u23f8",      # ⏸
    "auto": "\u25b6\u25b6",  # ▶▶
    "edit": "\u25b6\u25b6",  # ▶▶
}


def _sub_mode_line() -> list[tuple[str, str]]:
    """Format the sub-mode indicator line (shown only when mode has a sub-mode)."""
    name = _sub_mode_name()
    if not name:
        return [("", "")]
    icon = _SUB_MODE_ICONS.get(name, "\u25b6\u25b6")
    color_class = f"class:submode-{name}"
    return [
        (color_class, f"  {icon} "),
        (color_class, f"{name} mode on "),
        ("class:submode-hint", "(shift+tab to cycle)"),
    ]


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


_MENU_MAX_HEIGHT = 16  # menu rows cap


def _scroll_terminal_up(lines: int) -> None:
    """Force the terminal to scroll up by writing raw bytes to fd 1.

    Bypasses sys.stdout and patch_stdout — goes straight to the terminal
    so newlines actually scroll instead of being captured as scrollback.
    """
    import os
    try:
        data = ("\n" * lines + f"\033[{lines}A").encode()
        os.write(1, data)
    except OSError:
        pass


def _reserve_terminal_space() -> None:
    """Scroll the terminal up so the widget + menu fit below the cursor."""
    menu = _mode_stack.get_menu() if _mode_stack else []
    widget_rows = 3  # mode bar + input + separator
    if _processing_message:
        widget_rows += 1
    if _sub_mode_name():
        widget_rows += 1
    if _ctrlc_active():
        widget_rows += 1
    menu_rows = min(len(menu), _MENU_MAX_HEIGHT)
    reserve = widget_rows + menu_rows + 1
    _scroll_terminal_up(reserve)


def get_input() -> str | None:
    """Prompt for one line of input with mode bar above and separator below.

    The widget stays in scrollback after submission — no erasing. This keeps
    the mode bar and user input visible as history.
    """
    _reserve_terminal_space()

    sep = "\u2500" * os.get_terminal_size().columns
    completer = _DynamicCompleter()

    buf = Buffer(
        history=_history,
        completer=completer,
        complete_while_typing=True,
    )

    # Intercept `buf.insert_text` so ANY insertion over
    # PASTE_ABBREV_THRESHOLD chars gets abbreviated — covers bracketed
    # paste, clipboard yanks, and programmatic inserts. Keystroke-level
    # typing inserts 1 char at a time, well under the threshold, so
    # regular typing is unaffected.
    _orig_insert_text = buf.insert_text

    def _intercepted_insert(data, overwrite=False, move_cursor=True, fire_event=True):
        if len(data) > PASTE_ABBREV_THRESHOLD:
            data = _stash_paste(data.replace("\r\n", "\n"))
        _orig_insert_text(data, overwrite=overwrite, move_cursor=move_cursor, fire_event=fire_event)

    buf.insert_text = _intercepted_insert

    body = HSplit([
        ConditionalContainer(
            Window(
                FormattedTextControl(_status_line),
                height=1,
            ),
            filter=Condition(lambda: _processing_message is not None),
        ),
        Window(
            FormattedTextControl(lambda: [("class:separator", _mode_bar())]),
            height=1,
        ),
        Window(
            BufferControl(
                buffer=buf,
                input_processors=[BeforeInput("> ", style="class:prompt")],
            ),
            wrap_lines=True,
            dont_extend_height=True,
            height=Dimension(min=1, max=20),
        ),
        Window(FormattedTextControl(sep), height=1, style="class:separator"),
        ConditionalContainer(
            Window(
                FormattedTextControl(_sub_mode_line),
                height=1,
            ),
            filter=Condition(lambda: _sub_mode_name() is not None),
        ),
        ConditionalContainer(
            Window(
                FormattedTextControl(
                    lambda: [("class:ctrlc-hint", "Press Ctrl-C again to exit")]
                ),
                height=1,
            ),
            filter=Condition(_ctrlc_active),
        ),
        # Spacer that reserves vertical space for the completion menu float.
        # Only active when the completion menu is visible.
        ConditionalContainer(
            Window(height=Dimension(min=1, preferred=_MENU_MAX_HEIGHT)),
            filter=Condition(lambda: buf.complete_state is not None),
        ),
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
            return
        # No completion menu — cycle the mode's sub-mode (if any)
        if _mode_stack is not None:
            _mode_stack.current.cycle_sub_mode()

    @kb.add("enter")
    def _accept(event):
        if _has_menu(buf):
            buf.complete_state = None
        text = buf.text
        if text.strip():
            buf.append_to_history()
        event.app.exit(result=text)

    @kb.add("escape", eager=True)
    def _dismiss(event):
        if _has_menu(buf):
            buf.cancel_completion()

    @kb.add("c-c")
    def _ctrl_c(event):
        global _last_ctrlc
        import time as _time
        now = _time.monotonic()
        if _ctrlc_active():
            event.app.exit(result=None)
        else:
            _last_ctrlc = now
            event.app.invalidate()

    @kb.add("c-d")
    def _ctrl_d(event):
        event.app.exit(result=None)

    @kb.add(Keys.BracketedPaste)
    def _paste(event):
        """Collapse long pastes to a placeholder token.

        Pastes <= PASTE_ABBREV_THRESHOLD chars flow through unchanged.
        Longer ones get stashed and the buffer gets a short
        `[Pasted #N, K lines]` / `[Pasted #N, C chars]` marker — keeps
        the input widget readable and the submitted-line echo short.
        `expand_pastes()` restores the full content before commands /
        LLM handlers see it.
        """
        data = event.data.replace("\r\n", "\n")
        if len(data) > PASTE_ABBREV_THRESHOLD:
            buf.insert_text(_stash_paste(data))
        else:
            buf.insert_text(data)

    prompt_app = Application(
        layout=layout,
        key_bindings=kb,
        style=_style,
        full_screen=False,
        erase_when_done=True,
        refresh_interval=0.1,
    )
    prompt_app.timeoutlen = 0.05  # speed up escape handling
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
