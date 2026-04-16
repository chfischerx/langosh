"""Inline slash command handlers for the REPL."""

import os

import langosh.state as state

from .menus import ADMIN_COMMANDS_MENU, AGENT_EDIT_COMMANDS_MENU, AGENTS_COMMANDS_MENU, AGENTS_GRAPH_COMMANDS_MENU, CHAT_COMMANDS_MENU, CODE_COMMANDS_MENU


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
        elif state.current_mode == "main" and state.agent_editing:
            state.console.print("[bold]Agent edit mode commands:[/bold]")
            state.console.print("  [dim](any text)[/dim]                         Send as edit instruction")
            for cmd, desc in AGENT_EDIT_COMMANDS_MENU:
                state.console.print(f"  {cmd:<40} {desc}")
        elif state.current_mode == "admin":
            state.console.print("[bold]Admin mode commands:[/bold]")
            for cmd, desc in ADMIN_COMMANDS_MENU:
                state.console.print(f"  {cmd:<40} {desc}")
        elif state.active_graph_id:
            # agents mode with a graph selected
            state.console.print(f"[bold]Graph: {state.active_graph_id}[/bold]")
            for cmd, desc in AGENTS_GRAPH_COMMANDS_MENU:
                state.console.print(f"  {cmd:<40} {desc}")
        else:
            # agents mode — no graph selected
            state.console.print("[bold]Agents mode — select a graph to get started:[/bold]")
            for cmd, desc in AGENTS_COMMANDS_MENU:
                state.console.print(f"  {cmd:<40} {desc}")
        return "continue"

    if cmd_name == "chat":
        state.current_mode = "chat"
        turns = len([m for m in state.chat_messages if m["role"] == "user"])
        if turns:
            state.console.print(f"[bold cyan]Resumed chat mode[/bold cyan] [dim]({turns} turns)[/dim]")
        else:
            state.console.print("[bold cyan]Entered chat mode.[/bold cyan] Type text to send to the LLM.")
        state.console.print("[dim]Type / to see commands, /home to return.[/dim]")
        return "continue"

    if cmd_name == "code":
        state.current_mode = "code"
        turns = len([m for m in state.code_messages if m["role"] == "user"])
        if turns:
            state.console.print(f"[bold cyan]Resumed code mode[/bold cyan] [dim]({turns} turns, {state.code_sub_mode})[/dim]")
        else:
            state.console.print(f"[bold cyan]Entered code mode ({state.code_sub_mode}).[/bold cyan] Type a task — the LLM can read, write, and search files.")
        state.console.print("[dim]Type / to see commands, /home to return.[/dim]")
        return "continue"

    if cmd_name == "home":
        state.current_mode = "main"
        state.agent_editing = False
        state.console.print("[bold cyan]Home.[/bold cyan]")
        state.console.print("[dim]Type /help for commands.[/dim]")
        return "continue"

    if cmd_name == "admin":
        state.current_mode = "admin"
        state.console.print("[bold cyan]Admin mode.[/bold cyan] Manage langosh-server.")
        state.console.print("[dim]Type /help for commands, /home to return.[/dim]")
        return "continue"

    if cmd_name == "server":
        import asyncio

        from ..agents import server_client
        from ..settings import DEFAULT_SERVER_URL, get_server_url
        from ..settings import set as set_setting

        new_url = parts[1].strip() if len(parts) > 1 else None

        if new_url:
            # Light validation; allow http/https only.
            if not (new_url.startswith("http://") or new_url.startswith("https://")):
                state.console.print(
                    f"[bold red]Invalid URL:[/bold red] {new_url} "
                    "(must start with http:// or https://)"
                )
                return "continue"
            set_setting("server_url", new_url)
            state.console.print(f"[green]Set server_url to {new_url}[/green]")

        url = get_server_url()
        try:
            ok = asyncio.run(server_client.health_check())
        except Exception:
            ok = False
        status = "[green]reachable[/green]" if ok else "[red]unreachable[/red]"
        from ..agents.registry import langgraph_json_path
        from ..settings import get_agents_path

        state.console.print(f"[bold]server_url[/bold] [dim]({status})[/dim]: {url}")
        state.console.print(f"[bold]agents_path[/bold]: {get_agents_path()}")
        state.console.print(f"[bold]langgraph.json[/bold]: {langgraph_json_path()}")
        if url == DEFAULT_SERVER_URL and not new_url:
            state.console.print("[dim]Using built-in default. Override with /server <url> "
                                "or env LANGOSH_SERVER_URL.[/dim]")
        return "continue"

    if cmd_name == "select":
        import asyncio
        import questionary

        from ..agents import registry, server_client

        graph_id = parts[1].strip() if len(parts) > 1 else None
        if not graph_id:
            graphs = registry.list_graphs()
            if not graphs:
                state.console.print("[dim]No graphs in langgraph.json. Use /create first.[/dim]")
                return "continue"
            choices = [f"{gid} — {mod}" for gid, mod in graphs.items()]
            choice = questionary.rawselect("Select graph:", choices=choices).ask()
            if choice is None:
                state.console.print("[dim]Cancelled.[/dim]")
                return "continue"
            graph_id = choice.split(" — ")[0]

        try:
            # Fetch all assistants for this graph
            assistants = asyncio.run(server_client.list_graph_assistants(graph_id))
            if not assistants:
                # No assistants yet — create the default
                assistant = asyncio.run(server_client.ensure_assistant(graph_id))
            elif len(assistants) == 1:
                assistant = assistants[0]
            else:
                # Multiple assistants — let user pick
                choices = []
                for a in assistants:
                    name = a.get("name", "unnamed")
                    aid = a["assistant_id"][:8]
                    ctx = a.get("context") or a.get("config", {}).get("configurable", {})
                    ctx_str = ", ".join(f"{k}={v}" for k, v in ctx.items()) if ctx else "default"
                    choices.append(f"{name} ({aid}) — {ctx_str}")
                choice = questionary.rawselect("Select assistant:", choices=choices).ask()
                if choice is None:
                    state.console.print("[dim]Cancelled.[/dim]")
                    return "continue"
                idx = choices.index(choice)
                assistant = assistants[idx]

            thread = asyncio.run(server_client.create_thread())
        except Exception as e:
            state.console.print(f"[bold red]Server error:[/bold red] {e}")
            state.console.print("[dim]Is langosh-server running? Check /server.[/dim]")
            return "continue"

        state.active_graph_id = graph_id
        state.active_assistant_id = assistant["assistant_id"]
        state.active_thread_id = thread["thread_id"]
        state.agent_editing = False
        state.agent_messages.clear()
        state.agent_summary = ""

        aname = assistant.get("name", graph_id)
        state.console.print(
            f"[bold cyan]Selected: {aname}[/bold cyan] "
            f"[dim](graph {graph_id}, assistant {state.active_assistant_id[:8]}, "
            f"thread {state.active_thread_id[:8]})[/dim]"
        )
        return "continue"

    if cmd_name == "edit" and state.current_mode == "main":
        if not state.active_graph_id:
            state.console.print("[red]No graph selected. Use /select first.[/red]")
            return "continue"
        state.agent_editing = True
        state.console.print(f"[bold cyan]Editing graph ({state.agent_sub_mode}).[/bold cyan] Describe what to change or fix.")
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

        state.console.print("[bold]Create a new graph[/bold]\n")

        name = questionary.text(
            "Graph name:",
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

        # Runtime model — independent of the CLI's active model (which is only
        # used to drive the LLM that writes the JSON). Options:
        #   - server default (reads DEFAULT_MODEL from the server's env at runtime)
        #   - match the CLI's current active model
        #   - custom "provider:model-id" string
        cur_provider = state.active_model.get("provider") or ""
        cur_model_id = state.active_model.get("model_id") or ""
        cur_combined = f"{cur_provider}:{cur_model_id}" if cur_provider and cur_model_id else ""

        choices = ["Use server DEFAULT_MODEL (recommended)"]
        if cur_combined:
            choices.append(f"Match CLI active model ({cur_combined})")
        choices.append("Pick from model catalog")
        choices.append("Enter manually (provider:model-id)")

        model_choice = questionary.select("Runtime model for this graph:", choices=choices).ask()
        if model_choice is None:
            state.console.print("[dim]Cancelled.[/dim]")
            return "continue"

        if model_choice.startswith("Use server"):
            graph_model = None
        elif model_choice.startswith("Match CLI"):
            graph_model = cur_combined
        elif model_choice.startswith("Pick from"):
            if not state.model_list:
                state.console.print(
                    "[dim]No models cached yet. Run /fetchmodels first "
                    "(or pick 'Enter manually').[/dim]"
                )
                return "continue"
            catalog = sorted(f"{m.provider}:{m.id}" for m in state.model_list)
            graph_model = questionary.autocomplete(
                "Model (type to filter; Tab/arrow to complete):",
                choices=catalog,
                validate=lambda t: (
                    True if t and ":" in t and t in catalog else "Pick one from the list"
                ),
            ).ask()
            if graph_model is None:
                state.console.print("[dim]Cancelled.[/dim]")
                return "continue"
            graph_model = graph_model.strip()
        else:
            graph_model = questionary.text(
                "Model (format: provider:model-id, e.g. anthropic:claude-sonnet-4-5-20250929):",
                validate=lambda t: True if ":" in t and t.strip() else "Expected provider:model-id",
            ).ask()
            if graph_model is None:
                state.console.print("[dim]Cancelled.[/dim]")
                return "continue"
            graph_model = graph_model.strip()

        state.console.print()
        try:
            summary = create_agent(
                name.strip(), description.strip(), instructions.strip(), graph_model=graph_model,
            )
            state.console.print(f"\n[green]{summary}[/green]")
        except Exception as e:
            state.console.print(f"[bold red]Error creating agent:[/bold red] {e}")
        return "continue"

    if cmd_name in ("run", "test"):
        import asyncio
        import questionary

        from ..agents import server_client

        if not state.active_graph_id or not state.active_assistant_id or not state.active_thread_id:
            state.console.print("[red]No graph selected. Use /select first.[/red]")
            return "continue"

        # Parse --context key=val pairs and test input
        rest = parts[1].strip() if len(parts) > 1 else ""
        run_context: dict | None = None
        if "--context" in rest:
            # Split: everything before --context is ignored, everything after is key=val pairs
            before, _, ctx_str = rest.partition("--context")
            rest = before.strip()
            run_context = {}
            for pair in ctx_str.strip().split():
                if "=" in pair:
                    k, _, v = pair.partition("=")
                    run_context[k] = v

        if not rest:
            rest = questionary.text("Test message:").ask()
            if not rest or not rest.strip():
                state.console.print("[dim]Cancelled.[/dim]")
                return "continue"
        test_input = rest.strip()

        async def _on_event(event_type: str, data: dict) -> None:
            if event_type == "token":
                state.console.print(data.get("text", ""), end="", soft_wrap=True, highlight=False)
            elif event_type == "tool_call":
                state.console.print(f"\n[dim]  ↳ calling {data.get('name', '?')}...[/dim]")
            elif event_type == "tool_result":
                preview = data.get("preview", "")[:80]
                state.console.print(f"[dim]  ↳ done ({preview})[/dim]")
            elif event_type == "error":
                state.console.print(f"\n[bold red]Error:[/bold red] {data.get('message', '')}")

        state.agent_messages.append({"role": "user", "content": test_input})
        ctx_note = f" with context {run_context}" if run_context else ""
        state.console.print(f"\n[dim]Running on server (thread {state.active_thread_id[:8]}){ctx_note}...[/dim]\n")
        try:
            result = asyncio.run(
                server_client.stream_run(
                    assistant_id=state.active_assistant_id,
                    thread_id=state.active_thread_id,
                    messages=[{"role": "user", "content": test_input}],
                    context=run_context,
                    on_event=_on_event,
                )
            )
        except KeyboardInterrupt:
            if state.agent_messages and state.agent_messages[-1].get("role") == "user":
                state.agent_messages.pop()
            state.console.print("\n[yellow]Interrupted.[/yellow]")
            return "continue"
        except Exception as e:
            if state.agent_messages and state.agent_messages[-1].get("role") == "user":
                state.agent_messages.pop()
            state.console.print(f"\n[bold red]Error:[/bold red] {e}")
            return "continue"

        text = result.get("text", "")
        state.agent_messages.append({"role": "assistant", "content": text})
        turns = len([m for m in state.agent_messages if m["role"] == "user"])
        state.console.print(f"\n[dim]turn {turns} | run {result.get('run_id', '?')[:8]}[/dim]")
        return "continue"

    if cmd_name == "assistants":
        import asyncio

        from ..agents import server_client

        if not state.active_graph_id:
            state.console.print("[red]No graph selected. Use /select first.[/red]")
            return "continue"

        try:
            assistants = asyncio.run(server_client.list_graph_assistants(state.active_graph_id))
        except Exception as e:
            state.console.print(f"[bold red]Server error:[/bold red] {e}")
            return "continue"

        if not assistants:
            state.console.print("[dim]No assistants for this graph.[/dim]")
            return "continue"

        for a in assistants:
            name = a.get("name", "unnamed")
            aid = a["assistant_id"][:8]
            ctx = a.get("context") or a.get("config", {}).get("configurable", {})
            active = " [bold green]← active[/bold green]" if a["assistant_id"] == state.active_assistant_id else ""
            state.console.print(f"  [cyan]{name}[/cyan] ({aid}){active}")
            if ctx:
                for k, v in ctx.items():
                    state.console.print(f"    {k}: {v}")
        return "continue"

    if cmd_name == "assistant":
        import asyncio
        import json as _json

        import questionary

        from ..agents import registry, server_client

        sub = parts[1].strip().split(None, 1) if len(parts) > 1 else []
        sub_cmd = sub[0].lower() if sub else ""
        sub_arg = sub[1].strip() if len(sub) > 1 else ""

        if not state.active_graph_id:
            state.console.print("[red]No graph selected. Use /select first.[/red]")
            return "continue"

        if sub_cmd == "create":
            name = sub_arg or questionary.text("Assistant name:").ask()
            if not name or not name.strip():
                state.console.print("[dim]Cancelled.[/dim]")
                return "continue"
            name = name.strip()

            # Discover context schema from definition.json
            graph_dir = registry.graph_dir(state.active_graph_id)
            defn_path = graph_dir / "definition.json"
            ctx_schema = {}
            if defn_path.is_file():
                defn = _json.loads(defn_path.read_text())
                ctx_schema = defn.get("context", {})

            context = {}
            if ctx_schema:
                state.console.print("[dim]Set context values (Enter to keep default):[/dim]")
                for field, spec in ctx_schema.items():
                    default = spec.get("default", "")
                    val = questionary.text(f"  {field}:", default=str(default)).ask()
                    if val is None:
                        state.console.print("[dim]Cancelled.[/dim]")
                        return "continue"
                    # Try to parse as the right type
                    ftype = spec.get("type", "str")
                    if ftype == "int":
                        try:
                            context[field] = int(val)
                        except ValueError:
                            context[field] = val
                    elif ftype == "float":
                        try:
                            context[field] = float(val)
                        except ValueError:
                            context[field] = val
                    elif ftype == "bool":
                        context[field] = val.lower() in ("true", "1", "yes")
                    else:
                        context[field] = val
            else:
                state.console.print("[dim]No context schema in definition.json. Creating with defaults.[/dim]")

            try:
                assistant = asyncio.run(
                    server_client.create_assistant(
                        state.active_graph_id, name, context=context or None
                    )
                )
                aid = assistant["assistant_id"][:8]
                state.console.print(f"[green]Created assistant '{name}' ({aid})[/green]")

                # Offer to switch to new assistant
                switch = questionary.confirm("Use this assistant now?", default=True).ask()
                if switch:
                    thread = asyncio.run(server_client.create_thread())
                    state.active_assistant_id = assistant["assistant_id"]
                    state.active_thread_id = thread["thread_id"]
                    state.agent_messages.clear()
                    state.console.print(
                        f"[bold cyan]Switched to {name}[/bold cyan] "
                        f"[dim](thread {state.active_thread_id[:8]})[/dim]"
                    )
            except Exception as e:
                state.console.print(f"[bold red]Error:[/bold red] {e}")

        elif sub_cmd == "update":
            if not state.active_assistant_id:
                state.console.print("[red]No assistant active. Use /select first.[/red]")
                return "continue"

            graph_dir = registry.graph_dir(state.active_graph_id)
            defn_path = graph_dir / "definition.json"
            ctx_schema = {}
            if defn_path.is_file():
                defn = _json.loads(defn_path.read_text())
                ctx_schema = defn.get("context", {})

            if not ctx_schema:
                state.console.print("[dim]No context schema — nothing to update.[/dim]")
                return "continue"

            # Fetch current assistant context
            try:
                assistants = asyncio.run(server_client.list_graph_assistants(state.active_graph_id))
                current = next((a for a in assistants if a["assistant_id"] == state.active_assistant_id), None)
            except Exception as e:
                state.console.print(f"[bold red]Error:[/bold red] {e}")
                return "continue"

            current_ctx = (current.get("context") or {}) if current else {}
            context = {}
            state.console.print("[dim]Update context values (Enter to keep current):[/dim]")
            for field, spec in ctx_schema.items():
                current_val = current_ctx.get(field, spec.get("default", ""))
                val = questionary.text(f"  {field}:", default=str(current_val)).ask()
                if val is None:
                    state.console.print("[dim]Cancelled.[/dim]")
                    return "continue"
                ftype = spec.get("type", "str")
                if ftype == "int":
                    try:
                        context[field] = int(val)
                    except ValueError:
                        context[field] = val
                elif ftype == "float":
                    try:
                        context[field] = float(val)
                    except ValueError:
                        context[field] = val
                elif ftype == "bool":
                    context[field] = val.lower() in ("true", "1", "yes")
                else:
                    context[field] = val

            try:
                asyncio.run(server_client.update_assistant(state.active_assistant_id, context=context))
                state.console.print("[green]Assistant updated (new version created).[/green]")
            except Exception as e:
                state.console.print(f"[bold red]Error:[/bold red] {e}")

        elif sub_cmd == "delete":
            if not state.active_assistant_id:
                state.console.print("[red]No assistant active.[/red]")
                return "continue"
            confirm = questionary.confirm(
                f"Delete assistant {state.active_assistant_id[:8]}?", default=False
            ).ask()
            if confirm:
                try:
                    asyncio.run(server_client.delete_assistant(state.active_assistant_id))
                    state.console.print("[green]Assistant deleted.[/green]")
                    state.active_assistant_id = ""
                    state.active_thread_id = ""
                except Exception as e:
                    state.console.print(f"[bold red]Error:[/bold red] {e}")

        else:
            state.console.print(
                "[dim]Usage: /assistant create <name> | /assistant update | /assistant delete[/dim]"
            )
        return "continue"

    if cmd_name == "graph":
        import asyncio

        from ..agents import server_client

        graph_id = state.active_graph_id
        if not graph_id:
            state.console.print("[red]No graph selected. Use /select first.[/red]")
            return "continue"

        # Prefer importing the local module — gives a clean ASCII via langgraph's renderer
        try:
            import importlib

            mod = importlib.import_module(f"graphs.{graph_id}")
            local_graph = getattr(mod, "graph", None)
            if local_graph is not None:
                # Compile if needed — exported graph may be an uncompiled StateGraph
                from langgraph.graph import StateGraph
                compiled = local_graph.compile() if isinstance(local_graph, StateGraph) else local_graph
                state.console.print(f"\n[bold]Graph: {graph_id}[/bold]\n")
                state.console.print(compiled.get_graph().draw_ascii())
                return "continue"
        except Exception as e:
            state.console.print(f"[dim]Local import failed ({e}); fetching from server...[/dim]")

        # Fallback: fetch JSON from server
        if not state.active_assistant_id:
            state.console.print("[red]No active assistant; cannot fetch graph from server.[/red]")
            return "continue"
        try:
            data = asyncio.run(server_client.get_assistant_graph(state.active_assistant_id))
            state.console.print(f"\n[bold]Graph: {graph_id}[/bold] [dim](from server)[/dim]\n")
            import json
            state.console.print(json.dumps(data, indent=2))
        except Exception as e:
            state.console.print(f"[bold red]Error visualizing graph:[/bold red] {e}")
        return "continue"

    if cmd_name == "compile":
        import json as _json

        import questionary

        from ..agents import codegen, registry

        graph_id = parts[1].strip() if len(parts) > 1 else state.active_graph_id or None
        if not graph_id:
            graphs = registry.list_graphs()
            if not graphs:
                state.console.print("[dim]No graphs in langgraph.json.[/dim]")
                return "continue"
            choice = questionary.select("Select graph to compile:", choices=list(graphs.keys())).ask()
            if choice is None:
                state.console.print("[dim]Cancelled.[/dim]")
                return "continue"
            graph_id = choice

        folder = registry.graph_dir(graph_id)
        def_path = folder / "definition.json"
        if not def_path.is_file():
            state.console.print(
                f"[yellow]No definition.json in {folder}.[/yellow]\n"
                "[dim]This looks like a hand-written graph — edit `__init__.py` "
                "directly, then restart langosh-server.[/dim]"
            )
            return "continue"

        try:
            definition = _json.loads(def_path.read_text())
            funcs_dir = folder / "functions"
            functions: list[dict] = []
            if funcs_dir.is_dir():
                for fn_path in sorted(funcs_dir.glob("*.py")):
                    functions.append({"name": fn_path.stem, "code": fn_path.read_text()})
            init_path = codegen.write_compiled_graph(graph_id, definition, functions)
        except Exception as e:
            state.console.print(f"[bold red]Codegen failed:[/bold red] {e}")
            return "continue"

        state.console.print(
            f"[green]Regenerated {init_path}[/green]\n"
            "[dim]Restart langosh-server to apply.[/dim]"
        )
        return "continue"

    if cmd_name == "delete":
        import shutil

        import questionary

        from ..agents import registry

        graph_id = parts[1].strip() if len(parts) > 1 else state.active_graph_id or None
        if not graph_id:
            graphs = registry.list_graphs()
            if not graphs:
                state.console.print("[dim]No graphs to delete.[/dim]")
                return "continue"
            choice = questionary.select("Select graph to delete:", choices=list(graphs.keys())).ask()
            if choice is None:
                state.console.print("[dim]Cancelled.[/dim]")
                return "continue"
            graph_id = choice

        confirm = questionary.confirm(
            f"Remove graph '{graph_id}' from langgraph.json and delete its folder?",
            default=False,
        ).ask()
        if not confirm:
            state.console.print("[dim]Cancelled.[/dim]")
            return "continue"

        removed_entry = registry.remove_graph(graph_id)
        folder = registry.graph_dir(graph_id)
        if folder.exists():
            shutil.rmtree(folder)
            removed_folder = True
        else:
            removed_folder = False

        if state.active_graph_id == graph_id:
            state.active_graph_id = ""
            state.active_assistant_id = ""
            state.active_thread_id = ""
            state.agent_editing = False
            state.agent_messages.clear()
            state.agent_summary = ""

        if removed_entry or removed_folder:
            state.console.print(
                f"[green]Deleted {graph_id}.[/green] "
                f"[dim](langgraph.json: {'removed' if removed_entry else 'absent'}, "
                f"folder: {'removed' if removed_folder else 'absent'})[/dim]"
            )

            # Auto-commit and push to git in the agents repo
            import subprocess

            from ..settings import get_agents_path

            agents_path = str(get_agents_path())
            subprocess.run(["git", "add", "-A"], cwd=agents_path, capture_output=True)
            result = subprocess.run(
                ["git", "commit", "-m", f"Delete graph: {graph_id}"],
                cwd=agents_path, capture_output=True, text=True,
            )
            if result.returncode == 0:
                state.console.print(f"[dim]Committed: {result.stdout.strip().splitlines()[-1]}[/dim]")
                push = subprocess.run(
                    ["git", "push"], cwd=agents_path, capture_output=True, text=True,
                )
                if push.returncode == 0:
                    state.console.print("[dim]Pushed to remote.[/dim]")
                else:
                    state.console.print(f"[yellow]Push failed:[/yellow] [dim]{push.stderr.strip()}[/dim]")
            else:
                state.console.print(f"[dim]{result.stdout.strip() or result.stderr.strip()}[/dim]")

            state.console.print("[dim]Restart langosh-server to drop the registered graph.[/dim]")
        else:
            state.console.print(f"[red]Nothing found for graph: {graph_id}[/red]")
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

    if cmd_name == "deploy":
        import asyncio
        import subprocess
        from datetime import datetime

        from ..agents import server_client
        from ..settings import get_agents_path

        agents_path = str(get_agents_path())

        # 1. Check for uncommitted changes
        status = subprocess.run(
            ["git", "status", "--porcelain"], cwd=agents_path,
            capture_output=True, text=True,
        )
        if status.stdout.strip():
            # Stage and commit
            subprocess.run(["git", "add", "-A"], cwd=agents_path, capture_output=True)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M")
            result = subprocess.run(
                ["git", "commit", "-m", f"Deploy: {ts}"],
                cwd=agents_path, capture_output=True, text=True,
            )
            if result.returncode == 0:
                state.console.print(f"[green]Committed.[/green] [dim]{result.stdout.strip().splitlines()[-1]}[/dim]")
            else:
                state.console.print(f"[red]Commit failed:[/red] [dim]{result.stderr.strip()}[/dim]")
                return "continue"
        else:
            state.console.print("[dim]No uncommitted changes.[/dim]")

        # 2. Push
        push = subprocess.run(
            ["git", "push"], cwd=agents_path, capture_output=True, text=True,
        )
        if push.returncode == 0:
            out = push.stderr.strip() or push.stdout.strip()  # git push writes to stderr
            if "Everything up-to-date" in out:
                state.console.print("[dim]Already up to date with remote.[/dim]")
            else:
                state.console.print(f"[green]Pushed.[/green]")
        else:
            state.console.print(f"[yellow]Push failed:[/yellow] [dim]{push.stderr.strip()}[/dim]")

        # 3. Reload agents on server
        try:
            result = asyncio.run(server_client.reload_agents())
            state.console.print("[green]Server reloaded.[/green]")
            if isinstance(result, dict):
                sha = result.get("sha", "")[:7]
                prev = result.get("prev_sha", "")[:7]
                if sha and prev:
                    state.console.print(f"  [dim]{prev} → {sha}[/dim]")
                commits = result.get("commits", [])
                for c in commits:
                    csha = c.get("sha", "")[:7]
                    msg = c.get("message", "")
                    author = c.get("author", "")
                    state.console.print(f"  [cyan]{csha}[/cyan] {msg} [dim]({author})[/dim]")
                graphs = result.get("graphs", [])
                if graphs:
                    state.console.print(f"  [dim]Graphs: {', '.join(graphs)}[/dim]")
        except Exception as e:
            state.console.print(f"[yellow]Reload failed:[/yellow] [dim]{e}[/dim]")

        return "continue"

    if cmd_name == "list":
        import asyncio

        from rich.table import Table

        from ..agents import registry, server_client

        graphs = registry.list_graphs()
        if not graphs:
            from ..agents.registry import langgraph_json_path
            state.console.print(f"[dim]No graphs in {langgraph_json_path()}.[/dim]")
            return "continue"

        # Look up assistants per graph_id (best-effort — server may be down).
        # Health-check first (3s) so we don't hang on the SDK's default timeout.
        assistants_by_graph: dict[str, list[str]] = {}
        server_ok = False
        try:
            if asyncio.run(server_client.health_check()):
                async def _fetch():
                    return await asyncio.wait_for(
                        server_client.list_assistants(limit=100), timeout=5.0
                    )
                for a in asyncio.run(_fetch()):
                    assistants_by_graph.setdefault(a.get("graph_id", ""), []).append(a.get("assistant_id", "")[:8])
                server_ok = True
        except (asyncio.TimeoutError, Exception):
            server_ok = False

        table = Table(show_header=True, header_style="bold", padding=(0, 1))
        table.add_column("#", justify="right", style="dim")
        table.add_column("Graph ID")
        table.add_column("Module")
        table.add_column("Assistants" if server_ok else "Assistants (offline)", style="dim")

        for i, (gid, mod) in enumerate(graphs.items(), 1):
            assistants = ", ".join(assistants_by_graph.get(gid, []))
            table.add_row(str(i), gid, mod, assistants or "—")

        state.console.print(table)
        if not server_ok:
            state.console.print("[dim]Server unreachable; assistant column omitted.[/dim]")
        return "continue"

    if cmd_name in ("plan", "auto", "edit"):
        from ..settings import set as set_setting

        labels = {"plan": "All tool calls require approval", "auto": "Writes require approval", "edit": "No approvals"}
        if state.current_mode == "main":
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
        elif state.current_mode == "main" and state.active_graph_id:
            import asyncio

            from ..agents import server_client

            old_thread = state.active_thread_id
            try:
                if old_thread:
                    asyncio.run(server_client.delete_thread(old_thread))
                new_thread = asyncio.run(server_client.create_thread())
                state.active_thread_id = new_thread["thread_id"]
            except Exception as e:
                state.console.print(f"[bold red]Error resetting thread:[/bold red] {e}")
                return "continue"
            state.agent_messages.clear()
            state.agent_summary = ""
            state.console.print(
                f"[dim]Thread reset (was {old_thread[:8]}, now {state.active_thread_id[:8]}).[/dim]"
            )
        else:
            state.console.print("[dim]Nothing to clear.[/dim]")
        return "continue"

    # ── admin mode commands ────────────────────────────────────────────────

    if cmd_name == "info":
        import asyncio

        from ..agents import server_client

        try:
            info = asyncio.run(server_client.server_info())
        except Exception as e:
            state.console.print(f"[bold red]Server error:[/bold red] {e}")
            return "continue"

        for key, value in info.items():
            if isinstance(value, (dict, list)):
                import json as _json
                state.console.print(f"  [cyan]{key}:[/cyan] {_json.dumps(value, indent=2)}")
            else:
                state.console.print(f"  [cyan]{key}:[/cyan] {value}")
        return "continue"

    if cmd_name == "reload" and state.current_mode == "admin":
        import asyncio

        from ..agents import server_client

        try:
            result = asyncio.run(server_client.reload_agents())
            state.console.print("[green]Agents reloaded on server.[/green]")
            if isinstance(result, dict):
                sha = result.get("sha", "")[:7]
                prev = result.get("prev_sha", "")[:7]
                if sha and prev:
                    state.console.print(f"  [dim]{prev} → {sha}[/dim]")
                commits = result.get("commits", [])
                for c in commits:
                    csha = c.get("sha", "")[:7]
                    msg = c.get("message", "")
                    author = c.get("author", "")
                    state.console.print(f"  [cyan]{csha}[/cyan] {msg} [dim]({author})[/dim]")
                graphs = result.get("graphs", [])
                if graphs:
                    state.console.print(f"  [dim]Graphs: {', '.join(graphs)}[/dim]")
        except Exception as e:
            state.console.print(f"[bold red]Error:[/bold red] {e}")
        return "continue"

    if cmd_name == "keys" and state.current_mode == "admin":
        import asyncio

        from ..agents import server_client

        try:
            keys = asyncio.run(server_client.list_api_keys())
        except Exception as e:
            state.console.print(f"[bold red]Error:[/bold red] {e}")
            return "continue"

        if not keys:
            state.console.print("[dim]No API keys configured.[/dim]")
        else:
            for k in keys:
                name = k.get("name", "unnamed")
                created = k.get("created_at", "")
                short_key = k.get("key", k.get("api_key", ""))
                if isinstance(short_key, str) and len(short_key) > 12:
                    short_key = short_key[:8] + "..."
                state.console.print(f"  [cyan]{name}[/cyan] — {short_key} [dim]({created})[/dim]")
        return "continue"

    if cmd_name == "key" and state.current_mode == "admin":
        import asyncio

        import questionary

        from ..agents import server_client

        sub = parts[1].strip().split(None, 1) if len(parts) > 1 else []
        sub_cmd = sub[0].lower() if sub else ""
        sub_arg = sub[1].strip() if len(sub) > 1 else ""

        if sub_cmd == "create":
            name = sub_arg or questionary.text("Key name:").ask()
            if not name or not name.strip():
                state.console.print("[dim]Cancelled.[/dim]")
                return "continue"
            try:
                result = asyncio.run(server_client.create_api_key(name.strip()))
                key_val = result.get("key") or result.get("api_key") or str(result)
                state.console.print(f"[green]Created API key '{name.strip()}':[/green]")
                state.console.print(f"  [bold]{key_val}[/bold]")
                state.console.print("[dim]Save this key — it won't be shown again.[/dim]")
            except Exception as e:
                state.console.print(f"[bold red]Error:[/bold red] {e}")

        elif sub_cmd == "delete":
            name = sub_arg or questionary.text("Key name to delete:").ask()
            if not name or not name.strip():
                state.console.print("[dim]Cancelled.[/dim]")
                return "continue"
            confirm = questionary.confirm(f"Delete API key '{name.strip()}'?", default=False).ask()
            if confirm:
                try:
                    asyncio.run(server_client.delete_api_key(name.strip()))
                    state.console.print(f"[green]Deleted API key '{name.strip()}'.[/green]")
                except Exception as e:
                    state.console.print(f"[bold red]Error:[/bold red] {e}")

        elif sub_cmd == "rotate":
            name = sub_arg or questionary.text("Key name to rotate:").ask()
            if not name or not name.strip():
                state.console.print("[dim]Cancelled.[/dim]")
                return "continue"
            confirm = questionary.confirm(f"Rotate API key '{name.strip()}'?", default=False).ask()
            if confirm:
                try:
                    result = asyncio.run(server_client.rotate_api_key(name.strip()))
                    key_val = result.get("key") or result.get("api_key") or str(result)
                    state.console.print(f"[green]Rotated API key '{name.strip()}':[/green]")
                    state.console.print(f"  [bold]{key_val}[/bold]")
                    state.console.print("[dim]Save this key — the old one is now invalid.[/dim]")
                except Exception as e:
                    state.console.print(f"[bold red]Error:[/bold red] {e}")

        else:
            state.console.print(
                "[dim]Usage: /key create <name> | /key delete <name> | /key rotate <name>[/dim]"
            )
        return "continue"

    if cmd_name in ("back", "home"):
        state.current_mode = "main"
        state.agent_editing = False
        state.console.print("[dim]Home.[/dim]")
        return "continue"

    return "dispatch"
