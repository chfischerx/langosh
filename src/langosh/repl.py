"""Main REPL loop."""

import asyncio
import shlex
import subprocess
import sys

import click.exceptions
from prompt_toolkit.patch_stdout import patch_stdout

import langosh.state as state

from .input import get_input, model_display_name, set_mode_stack
from .modes import ModeStack
from .modes.main import MainMode
from .worker import run_in_background


import json
import os

_MODELS_CACHE_PATH = os.path.join(os.path.expanduser("~"), ".langosh", "models_cache.json")


def _save_models_cache() -> None:
    """Save model cache to disk."""
    os.makedirs(os.path.dirname(_MODELS_CACHE_PATH), exist_ok=True)
    data = {
        prov: [{"id": m.id, "name": m.name, "provider": m.provider} for m in models]
        for prov, models in state.model_cache.items()
    }
    with open(_MODELS_CACHE_PATH, "w") as f:
        json.dump(data, f, ensure_ascii=False)


def _load_models_cache() -> bool:
    """Load model cache from disk. Returns True if loaded."""
    if not os.path.isfile(_MODELS_CACHE_PATH):
        return False
    try:
        from .llm.model_catalog import ModelInfo

        with open(_MODELS_CACHE_PATH) as f:
            data = json.load(f)
        state.model_cache = {
            prov: [ModelInfo(id=m["id"], name=m["name"], provider=m["provider"]) for m in models]
            for prov, models in data.items()
        }
        return True
    except (json.JSONDecodeError, OSError, KeyError):
        return False


def _rebuild_model_list() -> None:
    """Rebuild the flat model_list from model_cache."""
    state.model_list.clear()
    for prov in sorted(state.model_cache):
        for m in state.model_cache[prov]:
            state.model_list.append(m)


def load_models() -> None:
    """Load models from disk cache, or fetch from APIs if no cache exists."""
    if state.model_cache:
        return

    if _load_models_cache():
        _rebuild_model_list()
        return

    fetch_models_from_apis()


def fetch_models_from_apis() -> None:
    """Fetch models from provider APIs, update cache and save to disk."""
    from .llm.model_catalog import fetch_models

    state.console.print("[dim]Fetching models from provider APIs...[/dim]")
    state.model_cache = asyncio.run(fetch_models())

    _rebuild_model_list()
    _save_models_cache()
    state.console.print(f"[dim]Loaded {len(state.model_list)} models from APIs[/dim]")


def _ensure_tool_cache() -> None:
    """Run /fetchtools on first launch so the builder has a catalog to work
    with. The cache is per-agents-path; subsequent runs re-use it silently.
    Users can refresh with /fetchtools at any time."""
    from .graphs import tool_cache
    from .modes.main import _do_fetchtools
    from .settings import get_agents_path

    if tool_cache.read_cache(get_agents_path()) is not None:
        return
    state.console.print("[dim]  tools:  no cache — running /fetchtools[/dim]")
    _do_fetchtools()


def repl(app) -> None:
    """Interactive REPL with hierarchical mode system."""
    from .history import load_history
    from .settings import get as get_setting

    chat_msgs, state.chat_summary = load_history("chat")
    code_msgs, state.code_summary = load_history("code")
    state.chat_messages.extend(chat_msgs)
    state.code_messages.extend(code_msgs)

    # Restore saved model selection
    saved_model = get_setting("active_model")
    if saved_model and isinstance(saved_model, dict):
        state.active_model["provider"] = saved_model.get("provider")
        state.active_model["model_id"] = saved_model.get("model_id")

    saved_sub_mode = get_setting("code_sub_mode")
    if saved_sub_mode in ("plan", "auto", "edit"):
        state.code_sub_mode = saved_sub_mode

    saved_agent_sub_mode = get_setting("agent_sub_mode")
    if saved_agent_sub_mode in ("plan", "auto", "edit"):
        state.agent_sub_mode = saved_agent_sub_mode

    from .settings import get_active_server_name, get_agents_path, get_server_url

    state.active_server_name = get_active_server_name()

    # Initialize mode stack
    mode_stack = ModeStack(MainMode())
    set_mode_stack(mode_stack)

    name = model_display_name() or "none"
    agents_path = str(get_agents_path())
    server_name = state.active_server_name
    server_url = get_server_url()
    state.console.print("[bold white]langosh[/bold white] [dim]v0.1.0[/dim]")
    state.console.print(f"[dim]  model:  {name}[/dim]")
    if server_name:
        state.console.print(f"[dim]  server: {server_name} ({server_url})[/dim]")
    else:
        state.console.print(f"[dim]  server: {server_url}[/dim]")
    state.console.print(f"[dim]  path:   {agents_path}[/dim]")

    _ensure_tool_cache()

    # Re-point Rich Console to sys.stdout so patch_stdout can intercept it
    from rich.console import Console
    from rich.theme import Theme

    with patch_stdout(raw=True):
        state.console = Console(theme=Theme({"dim": "grey70"}), file=sys.stdout)

        while True:
            line = get_input()

            if line is None:
                state.console.print("Bye!")
                break

            line = line.strip()
            if not line:
                continue

            # Echo the user input as clean history
            state.console.print(f"[dim]> {line}[/dim]")

            # --- Shell commands (any mode) ---
            if line.startswith("!"):
                cmd = line[1:].strip()
                if cmd:
                    try:
                        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
                        if result.stdout:
                            state.console.print(result.stdout.rstrip())
                        if result.stderr:
                            state.console.print(f"[red]{result.stderr.rstrip()}[/red]")
                        if result.returncode != 0:
                            state.console.print(f"[dim]exit code: {result.returncode}[/dim]")
                    except subprocess.TimeoutExpired:
                        state.console.print("[red]Command timed out (60s)[/red]")
                    except Exception as e:
                        state.console.print(f"[bold red]Error:[/bold red] {e}")
                continue

            # --- Slash commands (synchronous — may use questionary) ---
            if line.startswith("/"):
                cmd_body = line[1:]
                parts = cmd_body.split(None, 1)
                cmd_name = parts[0].lower() if parts else ""

                try:
                    action = mode_stack.handle_command(cmd_name, parts)
                except KeyboardInterrupt:
                    state.console.print("\n[yellow]Interrupted.[/yellow]")
                    continue
                except Exception as e:
                    state.console.print(f"[bold red]Error:[/bold red] {e}")
                    continue

                if action == "break":
                    break
                if action == "continue":
                    continue

                try:
                    args = shlex.split(cmd_body)
                    app(args, standalone_mode=False)
                except click.exceptions.ClickException as e:
                    e.show()
                except (click.exceptions.Abort, click.exceptions.Exit):
                    pass
                except SystemExit:
                    pass
                except KeyboardInterrupt:
                    state.console.print("\n[yellow]Interrupted.[/yellow]")
                except Exception as e:
                    state.console.print(f"[bold red]Error:[/bold red] {e}")
                continue

            # --- Non-slash input: run LLM call in background thread ---
            model_name = model_display_name() or "LLM"
            run_in_background(
                f"Calling {model_name}...",
                mode_stack.handle_free_text,
                line,
            )
