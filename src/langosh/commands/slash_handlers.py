"""Inline slash command handlers for the REPL."""

import os

import langosh.state as state

from .menus import AGENT_EDIT_COMMANDS_MENU, AGENTS_COMMANDS_MENU, CHAT_COMMANDS_MENU, CODE_COMMANDS_MENU, MAIN_COMMANDS


def handle_slash_command(cmd_name: str, parts: list[str]) -> str:
    """Handle a slash command. Returns 'continue', 'break', or 'dispatch' (for typer)."""

    if cmd_name in ("exit", "quit"):
        state.console.print("Bye!")
        return "break"

    if cmd_name == "help":
        if state.current_mode == "chat":
            state.console.print("[bold]Chat mode commands:[/bold]")
            state.console.print("  [dim](any text)[/dim]                         Send as LLM prompt")
            for cmd, desc in CHAT_COMMANDS_MENU:
                state.console.print(f"  {cmd:<40} {desc}")
        elif state.current_mode == "code":
            state.console.print("[bold]Code mode commands:[/bold]")
            state.console.print("  [dim](any text)[/dim]                         Send as coding task (with tools)")
            for cmd, desc in CODE_COMMANDS_MENU:
                state.console.print(f"  {cmd:<40} {desc}")
        elif state.current_mode == "agents" and state.agent_editing:
            state.console.print("[bold]Agent edit mode commands:[/bold]")
            state.console.print("  [dim](any text)[/dim]                         Send as edit instruction")
            for cmd, desc in AGENT_EDIT_COMMANDS_MENU:
                state.console.print(f"  {cmd:<40} {desc}")
        elif state.current_mode == "agents":
            state.console.print("[bold]Agents mode commands:[/bold]")
            for cmd, desc in AGENTS_COMMANDS_MENU:
                state.console.print(f"  {cmd:<40} {desc}")
        else:
            state.console.print("[bold]Main mode commands:[/bold]")
            for cmd, desc in MAIN_COMMANDS:
                state.console.print(f"  {cmd:<40} {desc}")
        return "continue"

    if cmd_name == "chat":
        state.current_mode = "chat"
        turns = len([m for m in state.chat_messages if m["role"] == "user"])
        if turns:
            state.console.print(f"[bold cyan]Resumed chat mode[/bold cyan] [dim]({turns} turns)[/dim]")
        else:
            state.console.print("[bold cyan]Entered chat mode.[/bold cyan] Type text to send to the LLM.")
        state.console.print("[dim]Type / to see commands, /back to return.[/dim]")
        return "continue"

    if cmd_name == "code":
        state.current_mode = "code"
        turns = len([m for m in state.code_messages if m["role"] == "user"])
        if turns:
            state.console.print(f"[bold cyan]Resumed code mode[/bold cyan] [dim]({turns} turns, {state.code_sub_mode})[/dim]")
        else:
            state.console.print(f"[bold cyan]Entered code mode ({state.code_sub_mode}).[/bold cyan] Type a task — the LLM can read, write, and search files.")
        state.console.print("[dim]Type / to see commands, /back to return.[/dim]")
        return "continue"

    if cmd_name == "agents":
        state.current_mode = "agents"
        state.console.print("[bold cyan]Entered agents mode.[/bold cyan] Manage your LangGraph agents.")
        state.console.print("[dim]Type / to see commands, /back to return.[/dim]")
        return "continue"

    if cmd_name == "select":
        import questionary

        from ..agents.editor import load_agent_history
        from ..agents.store import list_agents

        # Get agent_id from argument or prompt
        agent_id = parts[1].strip() if len(parts) > 1 else None
        if not agent_id:
            agents = list_agents()
            if not agents:
                state.console.print("[dim]No agents found. Use /create first.[/dim]")
                return "continue"
            choices = [f"{a['agent_id']} — {a.get('name', '')}" for a in agents]
            choice = questionary.rawselect("Select agent:", choices=choices).ask()
            if choice is None:
                state.console.print("[dim]Cancelled.[/dim]")
                return "continue"
            agent_id = choice.split(" — ")[0]

        state.active_agent_id = agent_id
        state.agent_editing = False

        # Load agent conversation history
        msgs, state.agent_summary = load_agent_history(agent_id)
        state.agent_messages.clear()
        state.agent_messages.extend(msgs)

        turns = len([m for m in state.agent_messages if m["role"] == "user"])
        from ..agents.store import load_agent
        agent_data = load_agent(agent_id)
        name = agent_data.get("metadata", {}).get("name", agent_id) if agent_data else agent_id
        if turns:
            state.console.print(f"[bold cyan]Selected: {name}[/bold cyan] [dim]({turns} conversation turns)[/dim]")
        else:
            state.console.print(f"[bold cyan]Selected: {name}[/bold cyan]")
        return "continue"

    if cmd_name == "edit" and state.current_mode == "agents":
        if not state.active_agent_id:
            state.console.print("[red]No agent selected. Use /select first.[/red]")
            return "continue"
        state.agent_editing = True
        state.console.print(f"[bold cyan]Editing agent ({state.agent_sub_mode}).[/bold cyan] Describe what to change or fix.")
        state.console.print("[dim]/done to exit, /test to run, /plan or /auto for approval mode.[/dim]")
        return "continue"

    if cmd_name == "done":
        if state.agent_editing:
            state.agent_editing = False
            state.console.print("[dim]Exited edit mode.[/dim]")
        return "continue"

    if cmd_name == "create":
        import questionary

        from ..agents.builder import create_agent

        state.console.print("[bold]Create a new agent[/bold]\n")

        name = questionary.text(
            "Agent name:",
            validate=lambda t: True if t.strip() else "Name cannot be empty",
        ).ask()
        if name is None:
            state.console.print("[dim]Cancelled.[/dim]")
            return "continue"

        description = questionary.text(
            "Description (what does this agent do?):",
            validate=lambda t: True if t.strip() else "Description cannot be empty",
        ).ask()
        if description is None:
            state.console.print("[dim]Cancelled.[/dim]")
            return "continue"

        instructions = questionary.text(
            "Build instructions (tools, workflow, behavior):",
            multiline=True,
        ).ask()
        if instructions is None or not instructions.strip():
            state.console.print("[dim]Cancelled.[/dim]")
            return "continue"

        state.console.print()
        try:
            summary = create_agent(name.strip(), description.strip(), instructions.strip())
            state.console.print(f"\n[green]{summary}[/green]")
        except Exception as e:
            state.console.print(f"[bold red]Error creating agent:[/bold red] {e}")
        return "continue"

    if cmd_name == "test":
        import asyncio

        import questionary
        from rich.table import Table

        from ..agents.runner import test_agent
        from ..agents.store import list_agents

        # Get agent_id from argument, active selection, or prompt
        agent_id = parts[1].strip() if len(parts) > 1 else state.active_agent_id or None
        if not agent_id:
            agents = list_agents()
            if not agents:
                state.console.print("[dim]No agents found. Use /create first.[/dim]")
                return "continue"
            choices = [f"{a['agent_id']} — {a.get('name', '')}" for a in agents]
            choice = questionary.select("Select agent to test:", choices=choices).ask()
            if choice is None:
                state.console.print("[dim]Cancelled.[/dim]")
                return "continue"
            agent_id = choice.split(" — ")[0]

        test_input = questionary.text("Test message:").ask()
        if test_input is None or not test_input.strip():
            state.console.print("[dim]Cancelled.[/dim]")
            return "continue"

        state.console.print(f"\n[dim]Running agent '{agent_id}'...[/dim]")
        result = asyncio.run(test_agent(agent_id, test_input.strip()))

        # Display events timeline
        events = result.get("events", [])
        if events:
            table = Table(show_header=True, header_style="bold", padding=(0, 1))
            table.add_column("#", justify="right", style="dim")
            table.add_column("Node")
            table.add_column("Details")
            for i, ev in enumerate(events, 1):
                node = ev.get("node", "?")
                preview = ev.get("preview", "")[:80]
                table.add_row(str(i), node, preview)
            state.console.print(table)

        # Display result
        duration = result.get("duration_ms", 0)
        status = result.get("status", "unknown")

        if status == "success":
            state.console.print(f"\n[bold green]Result[/bold green] [dim]({duration}ms)[/dim]")
            state.console.print(result.get("result", "(no output)"))
        elif status == "timeout":
            state.console.print(f"\n[bold red]Timed out[/bold red] [dim]({duration}ms)[/dim]")
        else:
            state.console.print(f"\n[bold red]Error[/bold red] [dim]({duration}ms)[/dim]")
            state.console.print(f"[red]{result.get('error', 'Unknown error')}[/red]")

        return "continue"

    if cmd_name == "graph":
        from ..agents.compiler import compile_agent
        from ..agents.runner import _load_functions
        from ..agents.store import load_agent

        agent_id = state.active_agent_id
        if not agent_id:
            state.console.print("[red]No agent selected. Use /select first.[/red]")
            return "continue"

        agent_data = load_agent(agent_id)
        if not agent_data or not agent_data.get("definition"):
            state.console.print(f"[red]No definition found for agent: {agent_id}[/red]")
            return "continue"

        try:
            functions = _load_functions(agent_id)
            graph = compile_agent(agent_data["definition"], functions)
            ascii_graph = graph.get_graph().draw_ascii()
            state.console.print(f"\n[bold]Graph: {agent_id}[/bold]\n")
            state.console.print(ascii_graph)
        except Exception as e:
            state.console.print(f"[bold red]Error visualizing graph:[/bold red] {e}")
        return "continue"

    if cmd_name == "delete":
        import questionary

        from ..agents.store import delete_agent, list_agents

        agent_id = parts[1].strip() if len(parts) > 1 else state.active_agent_id or None
        if not agent_id:
            agents = list_agents()
            if not agents:
                state.console.print("[dim]No agents found.[/dim]")
                return "continue"
            choices = [f"{a['agent_id']} — {a.get('name', '')}" for a in agents]
            choice = questionary.select("Select agent to delete:", choices=choices).ask()
            if choice is None:
                state.console.print("[dim]Cancelled.[/dim]")
                return "continue"
            agent_id = choice.split(" — ")[0]

        confirm = questionary.confirm(f"Delete agent '{agent_id}' and all its data?", default=False).ask()
        if not confirm:
            state.console.print("[dim]Cancelled.[/dim]")
            return "continue"

        if delete_agent(agent_id):
            # Clear state if this was the selected agent
            if state.active_agent_id == agent_id:
                state.active_agent_id = ""
                state.agent_editing = False
                state.agent_messages.clear()
                state.agent_summary = ""
            state.console.print(f"[green]Deleted agent: {agent_id}[/green]")
        else:
            state.console.print(f"[red]Agent not found: {agent_id}[/red]")
        return "continue"

    if cmd_name == "status":
        import subprocess

        result = subprocess.run(["git", "status", "--short"], capture_output=True, text=True)
        output = result.stdout.strip()
        if output:
            state.console.print(output)
        else:
            state.console.print("[dim]Nothing to commit, working tree clean.[/dim]")
        return "continue"

    if cmd_name == "commit":
        import subprocess

        import questionary

        # Get message from argument or prompt
        message = parts[1].strip() if len(parts) > 1 else None
        if not message:
            message = questionary.text("Commit message:").ask()
            if not message or not message.strip():
                state.console.print("[dim]Cancelled.[/dim]")
                return "continue"
            message = message.strip()

        # Stage all and commit
        result = subprocess.run(["git", "add", "-A"], capture_output=True, text=True)
        if result.returncode != 0:
            state.console.print(f"[red]{result.stderr.strip()}[/red]")
            return "continue"

        result = subprocess.run(["git", "commit", "-m", message], capture_output=True, text=True)
        if result.returncode != 0:
            stderr = result.stderr.strip()
            stdout = result.stdout.strip()
            state.console.print(f"[dim]{stdout or stderr}[/dim]")
        else:
            state.console.print(f"[green]{result.stdout.strip()}[/green]")
        return "continue"

    if cmd_name == "list":
        from rich.table import Table

        from ..agents.store import list_agents

        agents = list_agents()
        if not agents:
            state.console.print("[dim]No agents found. Use /create to build one.[/dim]")
            return "continue"

        table = Table(show_header=True, header_style="bold", padding=(0, 1))
        table.add_column("#", justify="right", style="dim")
        table.add_column("Name")
        table.add_column("Description")
        table.add_column("ID", style="dim")

        for i, a in enumerate(agents, 1):
            table.add_row(str(i), a.get("name", ""), a.get("description", "")[:60], a.get("agent_id", ""))

        state.console.print(table)
        return "continue"

    if cmd_name in ("plan", "auto", "edit"):
        from ..settings import set as set_setting

        labels = {"plan": "All tool calls require approval", "auto": "Writes require approval", "edit": "No approvals"}
        if state.current_mode == "agents":
            state.agent_sub_mode = cmd_name
            set_setting("agent_sub_mode", cmd_name)
        else:
            state.code_sub_mode = cmd_name
            set_setting("code_sub_mode", cmd_name)
        state.console.print(f"[bold cyan]{cmd_name}[/bold cyan] [dim]— {labels[cmd_name]}[/dim]")
        return "continue"

    if cmd_name == "debug":
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
                        state.console.print(f"    [dim]→ {preview[:200]}[/dim]")
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

    if cmd_name == "cls":
        os.system("cls" if os.name == "nt" else "clear")
        return "continue"

    if cmd_name == "fetchmodels":
        from ..repl import fetch_models_from_apis

        fetch_models_from_apis()
        return "continue"

    if cmd_name == "clc":
        from ..history import clear_history

        if state.current_mode == "chat":
            state.chat_messages.clear()
            state.chat_summary = ""
            clear_history("chat")
            state.console.print("[dim]Chat history cleared.[/dim]")
        elif state.current_mode == "code":
            state.code_messages.clear()
            state.code_summary = ""
            clear_history("code")
            state.console.print("[dim]Code history cleared.[/dim]")
        elif state.current_mode == "agents" and state.active_agent_id:
            from ..agents.editor import clear_agent_history

            state.agent_messages.clear()
            state.agent_summary = ""
            clear_agent_history(state.active_agent_id)
            state.console.print("[dim]Agent conversation cleared.[/dim]")
        else:
            state.console.print("[dim]Nothing to clear.[/dim]")
        return "continue"

    if cmd_name == "back":
        state.current_mode = "main"
        state.console.print("[dim]Back to main mode.[/dim]")
        return "continue"

    return "dispatch"
