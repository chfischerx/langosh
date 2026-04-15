"""Main REPL loop."""

import asyncio
import shlex
import subprocess

import click.exceptions

import langosh.state as state

from .commands.slash_handlers import handle_slash_command
from .input import erase_lines, get_input, model_display_name
from .queries import send_code_query, send_query


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

    with state.console.status("[dim]Fetching models from provider APIs...[/dim]"):
        state.model_cache = asyncio.run(fetch_models())

    _rebuild_model_list()
    _save_models_cache()
    state.console.print(f"[dim]Loaded {len(state.model_list)} models from APIs[/dim]")


def repl(app) -> None:
    """Interactive REPL with mode support and slash commands."""
    from .history import load_history
    from .settings import get as get_setting

    chat_msgs, state.chat_summary = load_history("chat")
    code_msgs, state.code_summary = load_history("code")
    state.chat_messages.extend(chat_msgs)
    state.code_messages.extend(code_msgs)

    # Restore saved model selection
    saved_model = get_setting("active_model")
    if saved_model and isinstance(saved_model, dict):
        provider = saved_model.get("provider")
        # Migrate old internal tag: aws_bedrock → bedrock_converse (valid
        # init_chat_model prefix).
        if provider == "aws_bedrock":
            provider = "bedrock_converse"
            from .settings import set as _set_setting
            _set_setting("active_model", {"provider": provider, "model_id": saved_model.get("model_id")})
        state.active_model["provider"] = provider
        state.active_model["model_id"] = saved_model.get("model_id")

    saved_sub_mode = get_setting("code_sub_mode")
    if saved_sub_mode in ("plan", "auto", "edit"):
        state.code_sub_mode = saved_sub_mode

    saved_agent_sub_mode = get_setting("agent_sub_mode")
    if saved_agent_sub_mode in ("plan", "auto", "edit"):
        state.agent_sub_mode = saved_agent_sub_mode

    state.console.print("[bold cyan]langosh[/bold cyan] interactive mode")
    name = model_display_name()
    if name:
        state.console.print(f"[dim]Model: {name}[/dim]")
    state.console.print("Type [bold]/help[/bold] for commands, [bold]/exit[/bold] to quit.")

    while True:
        line = get_input()
        erase_lines(3)

        if line is None:
            state.console.print("Bye!")
            break

        line = line.strip()
        if not line:
            continue

        # --- Shell commands (any mode) ---
        if line.startswith("!"):
            cmd = line[1:].strip()
            state.console.print(f"[dim]$ {cmd}[/dim]")
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

        # --- Slash commands (both modes) ---
        if line.startswith("/"):
            cmd_body = line[1:]
            parts = cmd_body.split(None, 1)
            cmd_name = parts[0].lower() if parts else ""

            state.console.print(f"[dim]> {line}[/dim]")

            try:
                action = handle_slash_command(cmd_name, parts)
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

            # Dispatch to typer commands
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

        # --- Non-slash input ---
        state.console.print(f"[dim]> {line}[/dim]")

        if state.current_mode == "chat":
            try:
                send_query(line)
            except KeyboardInterrupt:
                state.console.print("\n[yellow]Interrupted.[/yellow]")
            except Exception as e:
                state.console.print(f"[bold red]Error:[/bold red] {e}")
        elif state.current_mode == "code":
            try:
                send_code_query(line)
            except KeyboardInterrupt:
                state.console.print("\n[yellow]Interrupted.[/yellow]")
            except Exception as e:
                state.console.print(f"[bold red]Error:[/bold red] {e}")
        elif state.current_mode == "agents" and state.agent_editing:
            from .agents.editor import send_edit_query

            try:
                send_edit_query(line)
            except KeyboardInterrupt:
                state.console.print("\n[yellow]Interrupted.[/yellow]")
            except Exception as e:
                state.console.print(f"[bold red]Error:[/bold red] {e}")
        else:
            state.console.print("[dim]Use /help to see commands, or /chat or /code to enter LLM mode.[/dim]")
