"""Chat and code modes for LLM interaction."""

import langosh.state as state

from . import Mode, command


class ChatMode(Mode):
    """Chat mode — direct LLM conversation."""

    def path_label(self) -> str:
        return "chat"

    def on_enter(self) -> None:
        turns = len([m for m in state.chat_messages if m["role"] == "user"])
        if turns:
            state.console.print(f"[bold cyan]Resumed chat mode[/bold cyan] [dim]({turns} turns)[/dim]")
        else:
            state.console.print("[bold cyan]Entered chat mode.[/bold cyan] Type text to send to the LLM.")
        state.console.print("[dim]Type / to see commands, /back to return.[/dim]")

    def handle_free_text(self, text: str) -> None:
        from ..queries import send_query
        try:
            send_query(text)
        except KeyboardInterrupt:
            state.console.print("\n[yellow]Interrupted.[/yellow]")
        except Exception as e:
            state.console.print(f"[bold red]Error:[/bold red] {e}")

    @command("clear", "Clear conversation history")
    def cmd_clear(self, parts):
        from ..history import clear_history
        state.chat_messages.clear()
        state.chat_summary = ""
        clear_history("chat")
        state.console.print("[dim]Chat history cleared.[/dim]")
        return "continue"

    @command("compact", "Compact conversation history")
    def cmd_compact(self, parts):
        state.console.print("[dim]Not implemented yet.[/dim]")
        return "continue"

    @command("debug", "Inspect last LLM request/response")
    def cmd_debug(self, parts):
        return _handle_debug(parts)


class CodeMode(Mode):
    """Code mode — LLM with tool use (file read/write/exec)."""

    def path_label(self) -> str:
        return f"code:{state.code_sub_mode}"

    def on_enter(self) -> None:
        turns = len([m for m in state.code_messages if m["role"] == "user"])
        if turns:
            state.console.print(
                f"[bold cyan]Resumed code mode[/bold cyan] "
                f"[dim]({turns} turns, {state.code_sub_mode})[/dim]"
            )
        else:
            state.console.print(
                f"[bold cyan]Entered code mode ({state.code_sub_mode}).[/bold cyan] "
                "Type a task -- the LLM can read, write, and search files."
            )
        state.console.print("[dim]Type / to see commands, /back to return.[/dim]")

    def handle_free_text(self, text: str) -> None:
        from ..queries import send_code_query
        try:
            send_code_query(text)
        except KeyboardInterrupt:
            state.console.print("\n[yellow]Interrupted.[/yellow]")
        except Exception as e:
            state.console.print(f"[bold red]Error:[/bold red] {e}")

    @command("plan", "All tool calls require approval")
    def cmd_plan(self, parts):
        return _set_code_sub_mode("plan")

    @command("auto", "Writes require approval")
    def cmd_auto(self, parts):
        return _set_code_sub_mode("auto")

    @command("edit", "No approvals")
    def cmd_edit(self, parts):
        return _set_code_sub_mode("edit")

    @command("clear", "Clear conversation history")
    def cmd_clear(self, parts):
        from ..history import clear_history
        state.code_messages.clear()
        state.code_summary = ""
        clear_history("code")
        state.console.print("[dim]Code history cleared.[/dim]")
        return "continue"

    @command("compact", "Compact conversation history")
    def cmd_compact(self, parts):
        state.console.print("[dim]Not implemented yet.[/dim]")
        return "continue"

    @command("debug", "Inspect last LLM request/response")
    def cmd_debug(self, parts):
        return _handle_debug(parts)


# ── Shared helpers ──────────────────────────────────────────────────


def _set_code_sub_mode(mode: str) -> str:
    from ..settings import set as set_setting
    state.code_sub_mode = mode
    set_setting("code_sub_mode", mode)
    labels = {
        "plan": "All tool calls require approval",
        "auto": "Writes require approval",
        "edit": "No approvals",
    }
    state.console.print(f"[bold cyan]{mode}[/bold cyan] [dim]-- {labels[mode]}[/dim]")
    return "continue"


def _handle_debug(parts: list[str]) -> str:
    from ..queries import format_elapsed

    if not state.last_debug:
        state.console.print("[dim]No LLM calls yet.[/dim]")
        return "continue"
    sub = parts[1].lower() if len(parts) > 1 else ""
    d = state.last_debug
    if sub == "request":
        from ..llm.debug import last_request, syntax_json
        state.console.print("[bold]Raw JSON request body[/bold]")
        state.console.print(syntax_json(last_request, max_length=10000))
    elif sub == "response":
        from ..llm.debug import last_response, syntax_json
        state.console.print("[bold]Raw JSON response body[/bold]")
        state.console.print(syntax_json(last_response, max_length=10000))
    elif sub == "tools":
        tc = d.get("tool_calls", [])
        if not tc:
            state.console.print("[dim]No tool calls in last request.[/dim]")
        else:
            state.console.print(f"[bold]Tool calls[/bold] ({len(tc)})")
            for i, call in enumerate(tc, 1):
                state.console.print(f"\n  [bold]{i}. {call['name']}[/bold]")
                for k, v in call.get("input", {}).items():
                    val = str(v)[:120]
                    state.console.print(f"    [dim]{k}:[/dim] {val}")
                preview = call.get("result_preview", "")
                if preview:
                    state.console.print(f"    [dim]\u2192 {preview[:200]}[/dim]")
    else:
        from rich.table import Table
        table = Table(show_header=False, padding=(0, 2), box=None)
        table.add_column(style="bold")
        table.add_column()
        table.add_row("Mode", d["mode"])
        table.add_row("Provider", d["provider"])
        table.add_row("Model", d["model_name"])
        if d.get("sub_mode"):
            table.add_row("Sub-mode", d["sub_mode"])
        table.add_row("Elapsed", format_elapsed(d["elapsed"]))
        table.add_row("Input tokens", str(d["input_tokens"]))
        table.add_row("Output tokens", str(d["output_tokens"]))
        if d.get("cache_read_tokens"):
            table.add_row("Cache read", str(d["cache_read_tokens"]))
        if d.get("cache_creation_tokens"):
            table.add_row("Cache creation", str(d["cache_creation_tokens"]))
        table.add_row("Messages sent", str(d["message_count"]))
        if d.get("tools"):
            table.add_row("Tools", str(len(d["tools"])))
        tc = d.get("tool_calls", [])
        if tc:
            table.add_row("Tool calls", str(len(tc)))
        state.console.print(table)
        state.console.print("\n[dim]/debug request | /debug response | /debug tools[/dim]")
    return "continue"
