"""Exec mode — run graphs and manage assistants/threads/runs on a server."""

import asyncio

import langosh.state as state

from . import Mode, command


class _ThreadCommandsMixin:
    """Shared thread commands for graph and assistant modes.

    Expects the host class to have `graph_id` and optionally `assistant_id`.
    """

    def _thread_metadata_filter(self) -> dict:
        """Build metadata filter dict for the current scope."""
        meta = {"graph_id": self.graph_id}
        if getattr(self, "assistant_id", None):
            meta["assistant_id"] = self.assistant_id
        return meta

    @command("threads", "List all threads")
    def cmd_threads(self, parts):
        from ..server import server_client

        try:
            threads = asyncio.run(server_client.search_threads(
                limit=20, metadata=self._thread_metadata_filter(),
            ))
        except Exception as e:
            state.console.print(f"[bold red]Error:[/bold red] {e}")
            return "continue"

        if not threads:
            state.console.print("[dim]No threads found.[/dim]")
            return "continue"

        for t in threads:
            tid = t["thread_id"][:8]
            status = t.get("status", "?")
            updated = t.get("updated_at", "")[:16].replace("T", " ")
            meta = t.get("metadata") or {}
            name = meta.get("name", "")
            name_col = f"  {name}" if name else ""
            state.console.print(f"  {tid}  {status:12} {updated}{name_col}")
        return "continue"

    @command("delthread", "Delete a thread")
    def cmd_delthread(self, parts):
        import questionary
        from ..server import server_client

        try:
            threads = asyncio.run(server_client.search_threads(
                limit=20, metadata=self._thread_metadata_filter(),
            ))
        except Exception as e:
            state.console.print(f"[bold red]Error:[/bold red] {e}")
            return "continue"

        if not threads:
            state.console.print("[dim]No threads found.[/dim]")
            return "continue"

        choices = [questionary.Choice(title="\u2190 Back", value=None)]
        for t in threads:
            tid = t["thread_id"][:8]
            updated = t.get("updated_at", "")[:16].replace("T", " ")
            meta = t.get("metadata") or {}
            name = meta.get("name", "")
            label = f"{tid}  {updated}  {name}" if name else f"{tid}  {updated}"
            choices.append(questionary.Choice(title=label, value=t))

        picked = questionary.select("Delete which thread?", choices=choices).ask()
        if not picked:
            return "continue"

        confirm = questionary.confirm(f"Delete thread {picked['thread_id'][:8]}?", default=False).ask()
        if confirm:
            try:
                asyncio.run(server_client.delete_thread(picked["thread_id"]))
                state.console.print(f"[green]Deleted thread {picked['thread_id'][:8]}.[/green]")
            except Exception as e:
                state.console.print(f"[bold red]Error:[/bold red] {e}")
        return "continue"

    @command("delallthreads", "Delete all threads")
    def cmd_delallthreads(self, parts):
        import questionary
        from ..server import server_client

        try:
            threads = asyncio.run(server_client.search_threads(
                limit=100, metadata=self._thread_metadata_filter(),
            ))
        except Exception as e:
            state.console.print(f"[bold red]Error:[/bold red] {e}")
            return "continue"

        if not threads:
            state.console.print("[dim]No threads found.[/dim]")
            return "continue"

        confirm = questionary.confirm(
            f"Delete all {len(threads)} threads?", default=False
        ).ask()
        if not confirm:
            state.console.print("[dim]Cancelled.[/dim]")
            return "continue"

        deleted = 0
        for t in threads:
            try:
                asyncio.run(server_client.delete_thread(t["thread_id"]))
                deleted += 1
            except Exception:
                state.console.print(f"[yellow]Failed to delete {t['thread_id'][:8]}[/yellow]")
        state.console.print(f"[green]Deleted {deleted} thread(s).[/green]")
        return "continue"


def _deploy_work() -> None:
    """Perform git commit+push and server reload. Runs in worker thread."""
    import subprocess
    from datetime import datetime
    from ..server import server_client
    from ..settings import get_agents_path, is_langosh_server

    agents_path = str(get_agents_path())

    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=agents_path,
        capture_output=True, text=True,
    )
    if status.stdout.strip():
        subprocess.run(["git", "add", "-A"], cwd=agents_path, capture_output=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        result = subprocess.run(
            ["git", "commit", "-m", f"Deploy: {ts}"],
            cwd=agents_path, capture_output=True, text=True,
        )
        if result.returncode == 0:
            state.console.print(
                f"[green]Committed.[/green] [dim]{result.stdout.strip().splitlines()[-1]}[/dim]"
            )
        else:
            state.console.print(f"[red]Commit failed:[/red] [dim]{result.stderr.strip()}[/dim]")
            return
    else:
        state.console.print("[dim]No uncommitted changes.[/dim]")

    remotes = subprocess.run(
        ["git", "remote"], cwd=agents_path, capture_output=True, text=True,
    )
    if not remotes.stdout.strip():
        state.console.print("[dim]No git remote configured — skipping push.[/dim]")
    else:
        push = subprocess.run(
            ["git", "push"], cwd=agents_path, capture_output=True, text=True,
        )
        if push.returncode == 0:
            out = push.stderr.strip() or push.stdout.strip()
            if "Everything up-to-date" in out:
                state.console.print("[dim]Already up to date with remote.[/dim]")
            else:
                state.console.print("[green]Pushed.[/green]")
        else:
            state.console.print(f"[yellow]Push failed:[/yellow] [dim]{push.stderr.strip()}[/dim]")

    if is_langosh_server():
        try:
            result = asyncio.run(server_client.reload_agents())
            state.console.print("[green]Server reloaded.[/green]")
            if isinstance(result, dict):
                sha = result.get("sha", "")[:7]
                prev = result.get("prev_sha", "")[:7]
                if sha and prev:
                    state.console.print(f"  [dim]{prev} \u2192 {sha}[/dim]")
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
    else:
        state.console.print("[dim]Skipping reload (not a langosh server).[/dim]")


def _deploy() -> str:
    """Dispatch deploy to background worker."""
    from ..worker import run_in_background
    run_in_background("Deploying...", _deploy_work)
    return "continue"


async def _default_on_event(event_type, data):
    """Default event handler for streaming runs — prints tokens, tool calls, errors."""
    if event_type == "token":
        state.console.print(data.get("text", ""), end="", soft_wrap=True, highlight=False)
    elif event_type == "tool_call":
        state.console.print(f"\n[dim]  \u21b3 calling {data.get('name', '?')}...[/dim]")
    elif event_type == "tool_result":
        preview = data.get("preview", "")[:80]
        state.console.print(f"[dim]  \u21b3 done ({preview})[/dim]")
    elif event_type == "error":
        state.console.print(f"\n[bold red]Error:[/bold red] {data.get('message', '')}")


def _execute_run(exec_mode: str, assistant_id: str, thread_id: str | None,
                 messages: list[dict]) -> None:
    """Execute the run in the chosen mode. Called from a worker thread."""
    from ..server import server_client

    if exec_mode == "Stream output":
        result = asyncio.run(
            server_client.stream_run(
                assistant_id=assistant_id, thread_id=thread_id,
                messages=messages, on_event=_default_on_event,
            )
        )
        rid = result.get("run_id", "?")[:8]
        state.console.print(f"\n[dim]run {rid}[/dim]")

    elif exec_mode == "Wait for output":
        result = asyncio.run(
            server_client.wait_run(
                assistant_id=assistant_id, thread_id=thread_id,
                messages=messages,
            )
        )
        text = result.get("text", "")
        state.console.print(f"\n{text}")

    elif exec_mode == "Background":
        result = asyncio.run(
            server_client.background_run(
                assistant_id=assistant_id, thread_id=thread_id,
                messages=messages,
            )
        )
        run_id = result.get("run_id", "?")[:8]
        run_status = result.get("status", "?")
        state.console.print(f"[green]Run submitted.[/green] [dim]run {run_id} ({run_status})[/dim]")


def _stateless_test(graph_id: str, parts: list[str]) -> str:
    """Shared stateless test: ensure assistant, pick exec mode, prompt for message, run."""
    import questionary
    from ..server import server_client

    try:
        assistant = asyncio.run(server_client.ensure_assistant(graph_id))
    except Exception as e:
        state.console.print(f"[bold red]Server error:[/bold red] {e}")
        return "continue"

    aid = assistant["assistant_id"]

    exec_mode = questionary.select(
        "Execution mode:",
        choices=["Stream output", "Wait for output", "Background"],
    ).ask()
    if exec_mode is None:
        state.console.print("[dim]Cancelled.[/dim]")
        return "continue"

    rest = parts[1].strip() if len(parts) > 1 else ""
    if not rest:
        rest = questionary.text("Test message:").ask()
        if not rest or not rest.strip():
            state.console.print("[dim]Cancelled.[/dim]")
            return "continue"
    msg = rest.strip()

    messages = [{"role": "user", "content": msg}]

    from ..worker import run_in_background
    from ..input import model_display_name
    model = model_display_name() or "assistant"
    spinner_msg = f"Streaming {model}..." if exec_mode == "Stream output" else (
        f"Waiting for {model}..." if exec_mode == "Wait for output" else f"Submitting to {model}..."
    )
    run_in_background(spinner_msg, _execute_run, exec_mode, aid, None, messages)
    return "continue"


def _run_interactive(mode, parts, assistant_id: str, graph_id: str, *, metadata_filter: dict) -> str:
    """Shared /run flow: execution mode, thread selection, message, then execute."""
    import questionary
    from ..server import server_client

    # 1. Execution mode
    exec_mode = questionary.select(
        "Execution mode:",
        choices=["Stream output", "Wait for output", "Background"],
    ).ask()
    if exec_mode is None:
        state.console.print("[dim]Cancelled.[/dim]")
        return "continue"

    # 2. New thread or existing?
    new_thread = questionary.confirm("Create new thread?", default=True).ask()
    if new_thread is None:
        state.console.print("[dim]Cancelled.[/dim]")
        return "continue"

    if new_thread:
        thread_name = questionary.text("Thread name (optional):").ask()
        if thread_name is None:
            state.console.print("[dim]Cancelled.[/dim]")
            return "continue"

        meta = {"graph_id": graph_id, "assistant_id": assistant_id}
        if thread_name.strip():
            meta["name"] = thread_name.strip()

        try:
            thread = asyncio.run(server_client.create_thread(metadata=meta))
        except Exception as e:
            state.console.print(f"[bold red]Error creating thread:[/bold red] {e}")
            return "continue"
        tid = thread["thread_id"]
    else:
        # Select existing thread
        try:
            threads = asyncio.run(server_client.search_threads(
                limit=20, metadata=metadata_filter,
            ))
        except Exception as e:
            state.console.print(f"[bold red]Error:[/bold red] {e}")
            return "continue"

        if not threads:
            state.console.print("[dim]No threads found. Creating a new one.[/dim]")
            meta = {"graph_id": graph_id, "assistant_id": assistant_id}
            try:
                thread = asyncio.run(server_client.create_thread(metadata=meta))
            except Exception as e:
                state.console.print(f"[bold red]Error creating thread:[/bold red] {e}")
                return "continue"
            tid = thread["thread_id"]
        else:
            choices = [questionary.Choice(title="\u2190 Back", value=None)]
            for t in threads:
                t_id = t["thread_id"][:8]
                updated = t.get("updated_at", "")[:16].replace("T", " ")
                t_meta = t.get("metadata") or {}
                name = t_meta.get("name", "")
                label = f"{t_id}  {updated}  {name}" if name else f"{t_id}  {updated}"
                choices.append(questionary.Choice(title=label, value=t))

            picked = questionary.select("Select thread:", choices=choices).ask()
            if not picked:
                state.console.print("[dim]Cancelled.[/dim]")
                return "continue"
            tid = picked["thread_id"]

    # 3. Message
    rest = parts[1].strip() if len(parts) > 1 else ""
    if not rest:
        rest = questionary.text("Message:").ask()
        if not rest or not rest.strip():
            state.console.print("[dim]Cancelled.[/dim]")
            return "continue"
    msg = rest.strip()

    messages = [{"role": "user", "content": msg}]

    # 4. Dispatch execution to background worker (keeps prompt widget responsive)
    from ..worker import run_in_background
    from ..input import model_display_name
    model = model_display_name() or "assistant"
    spinner_msg = f"Streaming {model}..." if exec_mode == "Stream output" else (
        f"Waiting for {model}..." if exec_mode == "Wait for output" else f"Submitting to {model}..."
    )
    run_in_background(spinner_msg, _execute_run, exec_mode, assistant_id, tid, messages)
    return "continue"


class ExecMode(Mode):
    """Exec mode — select and run graphs on the active server."""

    def __init__(self, server_name: str):
        self.server_name = server_name

    def path_label(self) -> str:
        return f"exec[{self.server_name}]"

    def on_enter(self) -> None:
        state.console.print(
            f"[bold cyan]Exec mode[/bold cyan] [dim](server: {self.server_name})[/dim]"
        )
        state.console.print("[dim]Type /help for commands, /back to return.[/dim]")

    @command("list", "List all available graphs")
    def cmd_list(self, parts):
        from rich.table import Table
        from ..server import server_client

        try:
            assistants = asyncio.run(server_client.list_assistants(limit=100))
        except Exception as e:
            state.console.print(f"[bold red]Server error:[/bold red] {e}")
            return "continue"

        if not assistants:
            state.console.print("[dim]No graphs found on server.[/dim]")
            return "continue"

        # Group assistants by graph_id
        graphs: dict[str, list[str]] = {}
        for a in assistants:
            gid = a.get("graph_id", "?")
            name = a.get("name", a.get("assistant_id", "")[:8])
            graphs.setdefault(gid, []).append(name)

        table = Table(show_header=True, header_style="bold", padding=(0, 1))
        table.add_column("#", justify="right", style="dim")
        table.add_column("Graph ID")
        table.add_column("Assistants")

        for i, (gid, names) in enumerate(graphs.items(), 1):
            table.add_row(str(i), gid, ", ".join(names))

        state.console.print(table)
        return "continue"

    @command("select", "Select a graph")
    def cmd_select(self, parts):
        import questionary
        from ..server import server_client

        graph_id = parts[1].strip() if len(parts) > 1 else None
        if not graph_id:
            try:
                assistants = asyncio.run(server_client.list_assistants(limit=100))
            except Exception as e:
                state.console.print(f"[bold red]Server error:[/bold red] {e}")
                return "continue"

            graph_ids = sorted({a.get("graph_id", "") for a in assistants if a.get("graph_id")})
            if not graph_ids:
                state.console.print("[dim]No graphs found on server.[/dim]")
                return "continue"
            choice = questionary.select("Select graph:", choices=graph_ids).ask()
            if choice is None:
                state.console.print("[dim]Cancelled.[/dim]")
                return "continue"
            graph_id = choice

        self._stack.push(ExecGraphMode(self.server_name, graph_id))
        return "continue"

    @command("deploy", "Commit, push, and reload agents on the server")
    def cmd_deploy(self, parts):
        return _deploy()


class ExecGraphMode(_ThreadCommandsMixin, Mode):
    """Graph mode under exec — manage assistants, threads, and runs."""

    def __init__(self, server_name: str, graph_id: str):
        self.server_name = server_name
        self.graph_id = graph_id

    def path_label(self) -> str:
        return self.graph_id

    def on_enter(self) -> None:
        state.console.print(f"[bold cyan]Graph: {self.graph_id}[/bold cyan]")
        state.console.print("[dim]Type /help for commands, /back to return.[/dim]")

    @command("select", "Select an assistant")
    def cmd_select(self, parts):
        import questionary
        from ..server import server_client

        try:
            assistants = asyncio.run(server_client.list_graph_assistants(self.graph_id))
        except Exception as e:
            state.console.print(f"[bold red]Server error:[/bold red] {e}")
            return "continue"

        if not assistants:
            state.console.print("[dim]No assistants. Use /create to make one.[/dim]")
            return "continue"

        if len(assistants) == 1:
            assistant = assistants[0]
        else:
            choices = []
            for a in assistants:
                name = a.get("name", "unnamed")
                aid = a["assistant_id"][:8]
                ctx = a.get("context") or a.get("config", {}).get("configurable", {})
                ctx_str = ", ".join(f"{k}={v}" for k, v in ctx.items()) if ctx else "default"
                choices.append(questionary.Choice(title=f"{name} ({aid}) \u2014 {ctx_str}", value=a))
            choices.insert(0, questionary.Choice(title="\u2190 Back", value=None))
            assistant = questionary.select("Select assistant:", choices=choices).ask()
            if assistant is None:
                return "continue"

        self._stack.push(
            ExecAssistantMode(self.server_name, self.graph_id, assistant["assistant_id"],
                              assistant.get("name", self.graph_id))
        )
        return "continue"

    @command("thread", "Select a thread")
    def cmd_thread(self, parts):
        import questionary
        from ..server import server_client

        meta_filter = {"graph_id": self.graph_id}
        try:
            threads = asyncio.run(server_client.search_threads(limit=20, metadata=meta_filter))
        except Exception as e:
            state.console.print(f"[bold red]Error:[/bold red] {e}")
            return "continue"

        if not threads:
            state.console.print("[dim]No threads found. Use /run to create one.[/dim]")
            return "continue"

        choices = [questionary.Choice(title="\u2190 Back", value=None)]
        for t in threads:
            tid = t["thread_id"][:8]
            status = t.get("status", "?")
            updated = t.get("updated_at", "")[:16].replace("T", " ")
            meta = t.get("metadata") or {}
            name = meta.get("name", "")
            label = f"{tid}  {status:12} {updated}  {name}" if name else f"{tid}  {status:12} {updated}"
            choices.append(questionary.Choice(title=label, value=t))

        picked = questionary.select("Select thread:", choices=choices).ask()
        if not picked:
            return "continue"

        # Resolve assistant_id from thread metadata or use default
        thread_meta = picked.get("metadata") or {}
        aid = thread_meta.get("assistant_id", "")
        if not aid:
            try:
                assistant = asyncio.run(server_client.ensure_assistant(self.graph_id))
                aid = assistant["assistant_id"]
            except Exception:
                aid = ""

        self._stack.push(
            ExecThreadMode(self.server_name, self.graph_id, aid, picked["thread_id"])
        )
        return "continue"

    @command("create", "Create a new assistant with custom context")
    def cmd_create(self, parts):
        import json as _json
        import questionary
        from ..graphs import registry; from ..server import server_client

        name = parts[1].strip() if len(parts) > 1 else None
        if not name:
            name = questionary.text("Assistant name:").ask()
        if not name or not name.strip():
            state.console.print("[dim]Cancelled.[/dim]")
            return "continue"
        name = name.strip()

        graph_dir = registry.graph_dir(self.graph_id)
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
                server_client.create_assistant(self.graph_id, name, context=context or None)
            )
            aid = assistant["assistant_id"][:8]
            state.console.print(f"[green]Created assistant '{name}' ({aid})[/green]")
        except Exception as e:
            state.console.print(f"[bold red]Error:[/bold red] {e}")
        return "continue"

    @command("search", "Search for assistants")
    def cmd_search(self, parts):
        from ..server import server_client

        try:
            assistants = asyncio.run(server_client.list_graph_assistants(self.graph_id))
        except Exception as e:
            state.console.print(f"[bold red]Server error:[/bold red] {e}")
            return "continue"

        if not assistants:
            state.console.print("[dim]No assistants for this graph.[/dim]")
            return "continue"

        for a in assistants:
            name = a.get("name", "unnamed")
            aid = a["assistant_id"][:8]
            version = a.get("version", "")
            desc = a.get("description") or ""
            ctx = a.get("context") or a.get("config", {}).get("configurable", {})
            ver = f" v{version}" if version else ""
            state.console.print(f"  [cyan]{name}[/cyan] ({aid}{ver})")
            if desc:
                state.console.print(f"    [dim]{desc}[/dim]")
            if ctx:
                for k, v in ctx.items():
                    state.console.print(f"    {k}: {v}")
        return "continue"

    @command("show", "Display the graph")
    def cmd_show(self, parts):
        from ..server import server_client
        from langchain_core.runnables.graph import Graph

        try:
            assistant = asyncio.run(server_client.ensure_assistant(self.graph_id))
            data = asyncio.run(server_client.get_assistant_graph(assistant["assistant_id"]))
        except Exception as e:
            state.console.print(f"[bold red]Error:[/bold red] {e}")
            return "continue"

        # Reconstruct a drawable Graph from the server response
        g = Graph()
        node_map = {}
        for n in data.get("nodes", []):
            node = g.add_node(None, id=n["id"])
            node_map[n["id"]] = node
        for e in data.get("edges", []):
            src = node_map.get(e.get("source"))
            tgt = node_map.get(e.get("target"))
            if src and tgt:
                g.add_edge(src, tgt, conditional=e.get("conditional", False))

        state.console.print(f"\n[bold]Graph: {self.graph_id}[/bold]\n")
        state.console.print(g.draw_ascii())
        return "continue"

    @command("test", "Stateless run (no thread history)")
    def cmd_test(self, parts):
        return _stateless_test(self.graph_id, parts)

    @command("run", "Create a stateful run (default assistant)")
    def cmd_run(self, parts):
        from ..server import server_client

        try:
            assistant = asyncio.run(server_client.ensure_assistant(self.graph_id))
        except Exception as e:
            state.console.print(f"[bold red]Server error:[/bold red] {e}")
            return "continue"

        return _run_interactive(
            self, parts, assistant["assistant_id"], self.graph_id,
            metadata_filter={"graph_id": self.graph_id},
        )


class ExecAssistantMode(_ThreadCommandsMixin, Mode):
    """Assistant mode — run with a specific assistant, manage threads."""

    def __init__(self, server_name: str, graph_id: str, assistant_id: str, assistant_name: str = ""):
        self.server_name = server_name
        self.graph_id = graph_id
        self.assistant_id = assistant_id
        self.assistant_name = assistant_name or assistant_id[:8]

    def path_label(self) -> str:
        return self.assistant_name

    def on_enter(self) -> None:
        state.console.print(
            f"[bold cyan]Assistant: {self.assistant_name}[/bold cyan] "
            f"[dim]({self.assistant_id[:8]})[/dim]"
        )

    @command("thread", "Select a thread")
    def cmd_thread(self, parts):
        import questionary
        from ..server import server_client

        meta_filter = {"graph_id": self.graph_id, "assistant_id": self.assistant_id}
        try:
            threads = asyncio.run(server_client.search_threads(limit=20, metadata=meta_filter))
        except Exception as e:
            state.console.print(f"[bold red]Error:[/bold red] {e}")
            return "continue"

        if not threads:
            state.console.print("[dim]No threads found. Use /run to create one.[/dim]")
            return "continue"

        choices = [questionary.Choice(title="\u2190 Back", value=None)]
        for t in threads:
            tid = t["thread_id"][:8]
            status = t.get("status", "?")
            updated = t.get("updated_at", "")[:16].replace("T", " ")
            meta = t.get("metadata") or {}
            name = meta.get("name", "")
            label = f"{tid}  {status:12} {updated}  {name}" if name else f"{tid}  {status:12} {updated}"
            choices.append(questionary.Choice(title=label, value=t))

        picked = questionary.select("Select thread:", choices=choices).ask()
        if not picked:
            return "continue"

        self._stack.push(
            ExecThreadMode(
                self.server_name, self.graph_id, self.assistant_id,
                picked["thread_id"],
            )
        )
        return "continue"

    @command("show", "Display assistant details")
    def cmd_show(self, parts):
        from ..server import server_client

        try:
            a = asyncio.run(server_client.get_assistant(self.assistant_id))
        except Exception as e:
            state.console.print(f"[bold red]Error:[/bold red] {e}")
            return "continue"

        state.console.print(f"  [bold]Name[/bold]       {a.get('name', '?')}")
        state.console.print(f"  [bold]ID[/bold]         {a['assistant_id'][:8]}")
        state.console.print(f"  [bold]Graph[/bold]      {a.get('graph_id', '?')}")
        version = a.get("version", "")
        if version:
            state.console.print(f"  [bold]Version[/bold]    {version}")
        ctx = a.get("context") or a.get("config", {}).get("configurable", {})
        if ctx:
            state.console.print("  [bold]Context[/bold]")
            for k, v in ctx.items():
                state.console.print(f"    {k}: {v}")
        return "continue"

    @command("update", "Update assistant context")
    def cmd_update(self, parts):
        import json as _json
        import questionary
        from ..graphs import registry; from ..server import server_client

        graph_dir = registry.graph_dir(self.graph_id)
        defn_path = graph_dir / "definition.json"
        ctx_schema = {}
        if defn_path.is_file():
            defn = _json.loads(defn_path.read_text())
            ctx_schema = defn.get("context", {})

        if not ctx_schema:
            state.console.print("[dim]No context schema -- nothing to update.[/dim]")
            return "continue"

        try:
            assistants = asyncio.run(server_client.list_graph_assistants(self.graph_id))
            current = next((a for a in assistants if a["assistant_id"] == self.assistant_id), None)
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
            asyncio.run(server_client.update_assistant(self.assistant_id, context=context))
            state.console.print("[green]Assistant updated (new version created).[/green]")
        except Exception as e:
            state.console.print(f"[bold red]Error:[/bold red] {e}")
        return "continue"

    @command("delete", "Delete the assistant")
    def cmd_delete(self, parts):
        import questionary
        from ..server import server_client

        confirm = questionary.confirm(
            f"Delete assistant '{self.assistant_name}'?", default=False
        ).ask()
        if not confirm:
            state.console.print("[dim]Cancelled.[/dim]")
            return "continue"

        try:
            asyncio.run(server_client.delete_assistant(self.assistant_id))
            state.console.print("[green]Assistant deleted.[/green]")
            self._stack.pop()
        except Exception as e:
            state.console.print(f"[bold red]Error:[/bold red] {e}")
        return "continue"

    @command("test", "Stateless run")
    def cmd_test(self, parts):
        import questionary
        from ..server import server_client

        rest = parts[1].strip() if len(parts) > 1 else ""
        if not rest:
            rest = questionary.text("Test message:").ask()
            if not rest or not rest.strip():
                state.console.print("[dim]Cancelled.[/dim]")
                return "continue"
        msg = rest.strip()

        async def _on_event(event_type, data):
            if event_type == "token":
                state.console.print(data.get("text", ""), end="", soft_wrap=True, highlight=False)
            elif event_type == "tool_call":
                state.console.print(f"\n[dim]  \u21b3 calling {data.get('name', '?')}...[/dim]")
            elif event_type == "tool_result":
                preview = data.get("preview", "")[:80]
                state.console.print(f"[dim]  \u21b3 done ({preview})[/dim]")
            elif event_type == "error":
                state.console.print(f"\n[bold red]Error:[/bold red] {data.get('message', '')}")

        state.console.print(f"\n[dim]Stateless run...[/dim]\n")
        try:
            asyncio.run(
                server_client.stream_run(
                    assistant_id=self.assistant_id,
                    thread_id=None,
                    messages=[{"role": "user", "content": msg}],
                    on_event=_on_event,
                )
            )
        except KeyboardInterrupt:
            state.console.print("\n[yellow]Interrupted.[/yellow]")
        except Exception as e:
            state.console.print(f"\n[bold red]Error:[/bold red] {e}")
        state.console.print()
        return "continue"

    @command("run", "Create a stateful run")
    def cmd_run(self, parts):
        return _run_interactive(
            self, parts, self.assistant_id, self.graph_id,
            metadata_filter={"graph_id": self.graph_id, "assistant_id": self.assistant_id},
        )
        return "continue"


class ExecThreadMode(Mode):
    """Thread mode — inspect and manage a specific thread."""

    def __init__(self, server_name: str, graph_id: str, assistant_id: str, thread_id: str):
        self.server_name = server_name
        self.graph_id = graph_id
        self.assistant_id = assistant_id
        self.thread_id = thread_id

    def path_label(self) -> str:
        return self.thread_id[:8]

    def on_enter(self) -> None:
        state.console.print(f"[bold cyan]Thread: {self.thread_id[:8]}[/bold cyan]")

    @command("details", "Show thread details")
    def cmd_details(self, parts):
        from ..server import server_client

        try:
            thread = asyncio.run(server_client.get_thread(self.thread_id))
        except Exception as e:
            state.console.print(f"[bold red]Error:[/bold red] {e}")
            return "continue"

        state.console.print(f"  [bold]Thread[/bold]   {thread['thread_id'][:8]}")
        state.console.print(f"  [bold]Status[/bold]   {thread.get('status', '?')}")
        state.console.print(f"  [bold]Created[/bold]  {thread.get('created_at', '')[:16].replace('T', ' ')}")
        state.console.print(f"  [bold]Updated[/bold]  {thread.get('updated_at', '')[:16].replace('T', ' ')}")
        return "continue"

    @command("state", "Show the thread state")
    def cmd_state(self, parts):
        import json as _json
        from ..server import server_client

        try:
            ts = asyncio.run(server_client.get_thread_state(self.thread_id))
        except Exception as e:
            state.console.print(f"[bold red]Error:[/bold red] {e}")
            return "continue"

        messages = (ts.get("values") or {}).get("messages", [])
        if messages:
            state.console.print(f"[bold]Conversation[/bold] ({len(messages)} messages)\n")
            for msg in messages:
                kwargs = msg.get("kwargs", msg)
                role = kwargs.get("type", "")
                content = kwargs.get("content", "")
                if isinstance(content, list):
                    content = "".join(
                        b.get("text", "") for b in content
                        if isinstance(b, dict) and b.get("type") == "text"
                    )
                if role in ("human", "HumanMessage"):
                    state.console.print(f"  [bold]>[/bold] {content}")
                elif role in ("ai", "AIMessage", "AIMessageChunk"):
                    preview = content[:200] + ("..." if len(content) > 200 else "")
                    state.console.print(f"  [dim]{preview}[/dim]")
                state.console.print()
        else:
            state.console.print("[dim]No messages yet.[/dim]")
        return "continue"

    @command("history", "Show the thread history")
    def cmd_history(self, parts):
        from ..server import server_client

        try:
            history = asyncio.run(server_client.get_thread_history(self.thread_id))
        except Exception as e:
            state.console.print(f"[bold red]Error:[/bold red] {e}")
            return "continue"

        if not history:
            state.console.print("[dim]No history.[/dim]")
            return "continue"

        for i, checkpoint in enumerate(history):
            ts = checkpoint.get("created_at", "")[:16].replace("T", " ")
            cid = checkpoint.get("checkpoint_id", "?")[:8]
            state.console.print(f"  {i + 1}. [cyan]{cid}[/cyan]  {ts}")
        return "continue"

    @command("delete", "Delete the thread")
    def cmd_delete(self, parts):
        import questionary
        from ..server import server_client

        confirm = questionary.confirm(f"Delete thread {self.thread_id[:8]}?", default=False).ask()
        if not confirm:
            state.console.print("[dim]Cancelled.[/dim]")
            return "continue"

        try:
            asyncio.run(server_client.delete_thread(self.thread_id))
            state.console.print(f"[green]Deleted thread {self.thread_id[:8]}.[/green]")
            self._stack.pop()
        except Exception as e:
            state.console.print(f"[bold red]Error:[/bold red] {e}")
        return "continue"

    @command("update", "Update the thread")
    def cmd_update(self, parts):
        state.console.print("[dim]Not implemented yet.[/dim]")
        return "continue"

    @command("runs", "List runs for this thread")
    def cmd_runs(self, parts):
        from ..server import server_client

        try:
            runs = asyncio.run(server_client.list_runs(self.thread_id))
        except Exception as e:
            state.console.print(f"[bold red]Error:[/bold red] {e}")
            return "continue"

        if not runs:
            state.console.print("[dim]No runs for this thread.[/dim]")
            return "continue"

        for r in runs:
            rid = r.get("run_id", "?")[:8]
            run_status = r.get("status", "?")
            created = r.get("created_at", "")[:16].replace("T", " ")
            state.console.print(f"  [cyan]{rid}[/cyan]  {run_status:12}  {created}")
        return "continue"

    @command("select", "Select a run")
    def cmd_select(self, parts):
        import questionary
        from ..server import server_client

        try:
            runs = asyncio.run(server_client.list_runs(self.thread_id))
        except Exception as e:
            state.console.print(f"[bold red]Error:[/bold red] {e}")
            return "continue"

        if not runs:
            state.console.print("[dim]No runs.[/dim]")
            return "continue"

        choices = [questionary.Choice(title="\u2190 Back", value=None)]
        for r in runs:
            rid = r.get("run_id", "?")[:8]
            run_status = r.get("status", "?")
            created = r.get("created_at", "")[:16].replace("T", " ")
            choices.append(questionary.Choice(title=f"{rid}  {run_status:12}  {created}", value=r))

        picked = questionary.select("Select run:", choices=choices).ask()
        if not picked:
            return "continue"

        self._stack.push(
            ExecRunMode(self.server_name, self.graph_id, self.assistant_id,
                        self.thread_id, picked["run_id"])
        )
        return "continue"


class ExecRunMode(Mode):
    """Run mode — inspect or cancel a specific run."""

    def __init__(self, server_name: str, graph_id: str, assistant_id: str,
                 thread_id: str, run_id: str):
        self.server_name = server_name
        self.graph_id = graph_id
        self.assistant_id = assistant_id
        self.thread_id = thread_id
        self.run_id = run_id

    def path_label(self) -> str:
        return self.run_id[:8]

    def on_enter(self) -> None:
        state.console.print(f"[bold cyan]Run: {self.run_id[:8]}[/bold cyan]")

    @command("details", "Get details for this run")
    def cmd_details(self, parts):
        state.console.print("[dim]Not implemented yet.[/dim]")
        return "continue"

    @command("delete", "Delete this run")
    def cmd_delete(self, parts):
        state.console.print("[dim]Not implemented yet.[/dim]")
        return "continue"

    @command("cancel", "Cancel this run")
    def cmd_cancel(self, parts):
        state.console.print("[dim]Not implemented yet.[/dim]")
        return "continue"
