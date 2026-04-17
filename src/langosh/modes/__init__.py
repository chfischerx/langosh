"""Hierarchical mode system for the langosh CLI.

Provides Mode (base class), ModeStack (push/pop navigation), and the
@command decorator for registering slash commands on mode classes.
"""

from __future__ import annotations

import os
from typing import Callable

import langosh.state as state


# ── @command decorator ──────────────────────────────────────────────


def command(name: str, description: str):
    """Register a method as a slash command on a Mode subclass."""
    def decorator(fn: Callable) -> Callable:
        fn._cmd_name = name
        fn._cmd_desc = description
        return fn
    return decorator


# ── Base Mode ───────────────────────────────────────────────────────


class Mode:
    """Abstract base class for all CLI modes."""

    _commands: dict[str, tuple[Callable, str]]
    _stack: ModeStack  # set by ModeStack.push()

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls._commands = {}
        for name in list(vars(cls)):
            attr = getattr(cls, name, None)
            if callable(attr) and hasattr(attr, "_cmd_name"):
                cls._commands[attr._cmd_name] = (attr, attr._cmd_desc)

    def path_label(self) -> str:
        """Label for this mode in the mode bar."""
        return self.__class__.__name__.lower().replace("mode", "")

    def get_menu(self) -> list[tuple[str, str]]:
        """Return (command_string, description) pairs for help + completion."""
        items = []
        for cmd_name, (_, desc) in sorted(self._commands.items()):
            items.append((f"/{cmd_name}", desc))
        items.extend([
            ("/help", "Show available commands"),
            ("/back", "Go back to parent mode"),
            ("/cls", "Clear screen"),
            ("/exit", "Quit"),
        ])
        return items

    def handle_command(self, cmd_name: str, parts: list[str]) -> str:
        """Dispatch a slash command. Returns 'continue', 'break', or 'dispatch'."""
        if cmd_name in self._commands:
            method, _ = self._commands[cmd_name]
            return method(self, parts)
        return "dispatch"

    def handle_free_text(self, text: str) -> None:
        """Handle non-slash input. Override in modes that accept free text."""
        state.console.print("[dim]Type /help for commands.[/dim]")

    def on_enter(self) -> None:
        """Called when this mode is pushed onto the stack."""

    def on_exit(self) -> None:
        """Called when this mode is popped from the stack."""

    def on_resume(self) -> None:
        """Called when a child mode is popped and this mode is back on top."""


# ── Mode Stack ──────────────────────────────────────────────────────


class ModeStack:
    """Manages the hierarchical mode stack. Top of stack = active mode."""

    def __init__(self, root: Mode):
        self._stack: list[Mode] = [root]
        root._stack = self

    @property
    def current(self) -> Mode:
        return self._stack[-1]

    @property
    def path(self) -> str:
        if len(self._stack) == 1:
            return self._stack[0].path_label()
        return ":".join(m.path_label() for m in self._stack[1:])

    @property
    def depth(self) -> int:
        return len(self._stack)

    def push(self, mode: Mode) -> None:
        mode._stack = self
        mode.on_enter()
        self._stack.append(mode)

    def pop(self) -> Mode | None:
        if len(self._stack) <= 1:
            return None
        exiting = self._stack.pop()
        exiting.on_exit()
        self._stack[-1].on_resume()
        return exiting

    def pop_to_root(self) -> None:
        while len(self._stack) > 1:
            self.pop()

    def get_menu(self) -> list[tuple[str, str]]:
        return self.current.get_menu()

    def handle_command(self, cmd_name: str, parts: list[str]) -> str:
        """Dispatch: universal commands first, then delegate to current mode."""
        if cmd_name in ("exit", "quit"):
            state.console.print("Bye!")
            return "break"
        if cmd_name == "help":
            self._show_help()
            return "continue"
        if cmd_name == "back":
            if self.pop() is None:
                state.console.print("[dim]Already at root.[/dim]")
            return "continue"
        if cmd_name == "home":
            self.pop_to_root()
            return "continue"
        if cmd_name == "cls":
            os.system("cls" if os.name == "nt" else "clear")
            return "continue"
        return self.current.handle_command(cmd_name, parts)

    def handle_free_text(self, text: str) -> None:
        self.current.handle_free_text(text)

    def _show_help(self) -> None:
        mode = self.current
        state.console.print(f"[bold]{self.path} commands:[/bold]")
        # Show free-text hint if the mode overrides handle_free_text
        if type(mode).handle_free_text is not Mode.handle_free_text:
            state.console.print("  [dim](any text)[/dim]                    Send as input")
        for cmd, desc in mode.get_menu():
            state.console.print(f"  {cmd:<30} {desc}")
