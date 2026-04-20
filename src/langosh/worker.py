"""Background worker for long-running LLM/server calls.

Runs work in a thread so the prompt_toolkit input widget stays visible
and responsive. Uses a single global lock — one worker at a time —
to avoid overlapping output or concurrent stdin reads.
"""

from __future__ import annotations

import threading
from typing import Callable

import langosh.state as state

from .input import set_processing

_lock = threading.Lock()


def run_in_background(message: str, fn: Callable, *args, **kwargs) -> bool:
    """Start fn in a background thread with the spinner showing `message`.

    Returns True if started, False if another worker is already active.
    """
    if not _lock.acquire(blocking=False):
        state.console.print("[dim]Still processing previous request...[/dim]")
        return False

    def _wrapped():
        set_processing(message)
        try:
            fn(*args, **kwargs)
        except KeyboardInterrupt:
            state.console.print("\n[yellow]Interrupted.[/yellow]")
        except Exception as e:
            state.console.print(f"[bold red]Error:[/bold red] {e}")
        finally:
            set_processing(None)
            _lock.release()

    threading.Thread(target=_wrapped, daemon=True).start()
    return True


def is_busy() -> bool:
    """Return True if a worker is currently running."""
    # acquire/release to peek at state
    if _lock.acquire(blocking=False):
        _lock.release()
        return False
    return True
