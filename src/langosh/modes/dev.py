"""Dev mode — local graph development in the langgraph repo."""

import langosh.state as state

from . import Mode, command


class _GitMixin:
    """Shared git commands for dev modes."""

    @command("status", "Show git status")
    def cmd_status(self, parts):
        import subprocess
        result = subprocess.run(["git", "status", "--short"], capture_output=True, text=True)
        output = result.stdout.strip()
        if output:
            state.console.print(output)
        else:
            state.console.print("[dim]Nothing to commit, working tree clean.[/dim]")
        return "continue"

    @command("commit", "Commit all changes")
    def cmd_commit(self, parts):
        import subprocess
        import questionary

        message = parts[1].strip() if len(parts) > 1 else None
        if not message:
            message = questionary.text("Commit message:").ask()
            if not message or not message.strip():
                state.console.print("[dim]Cancelled.[/dim]")
                return "continue"
            message = message.strip()

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

    @command("deploy", "Commit, push, and reload agents on the server")
    def cmd_deploy(self, parts):
        from .exec_ import _deploy
        return _deploy()


class DevMode(_GitMixin, Mode):
    """Dev mode — list, create, and select graphs from the local repo."""

    def path_label(self) -> str:
        server = state.active_server_name
        return f"dev[{server}]" if server else "dev"

    def on_enter(self) -> None:
        state.console.print("[bold cyan]Dev mode.[/bold cyan] Work with local graphs.")
        state.console.print("[dim]Type /help for commands, /back to return.[/dim]")

    @command("list", "List all graphs from the current repo")
    def cmd_list(self, parts):
        from ..agents import registry
        graphs = registry.list_graphs()
        if not graphs:
            from ..agents.registry import langgraph_json_path
            state.console.print(f"[dim]No graphs in {langgraph_json_path()}.[/dim]")
            return "continue"
        for i, (gid, mod) in enumerate(graphs.items(), 1):
            state.console.print(f"  {i}. [cyan]{gid}[/cyan] — {mod}")
        return "continue"

    @command("create", "Create a new graph with LLM guidance")
    def cmd_create(self, parts):
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

    @command("select", "Select an existing graph to work with")
    def cmd_select(self, parts):
        import questionary
        from ..agents import registry

        graph_id = parts[1].strip() if len(parts) > 1 else None
        if not graph_id:
            graphs = registry.list_graphs()
            if not graphs:
                state.console.print("[dim]No graphs in langgraph.json. Use /create first.[/dim]")
                return "continue"
            choices = list(graphs.keys())
            choice = questionary.select("Select graph:", choices=choices).ask()
            if choice is None:
                state.console.print("[dim]Cancelled.[/dim]")
                return "continue"
            graph_id = choice

        self._stack.push(DevGraphMode(graph_id))
        return "continue"


class DevGraphMode(_GitMixin, Mode):
    """Selected graph mode — LLM-driven editing with sub-mode control."""

    def __init__(self, graph_id: str):
        self.graph_id = graph_id
        self.llm_mode = state.agent_sub_mode  # normal/plan/auto

    def path_label(self) -> str:
        return f"{self.graph_id}:{self.llm_mode}"

    def on_enter(self) -> None:
        state.active_graph_id = self.graph_id
        state.agent_editing = True
        state.agent_messages.clear()
        state.agent_summary = ""
        state.console.print(
            f"[bold cyan]Editing {self.graph_id} ({self.llm_mode}).[/bold cyan] "
            "Describe what to change."
        )
        state.console.print("[dim]Type /help for commands, /back to exit.[/dim]")

    def on_exit(self) -> None:
        state.active_graph_id = ""
        state.agent_editing = False

    def handle_free_text(self, text: str) -> None:
        from ..agents.editor import send_edit_query
        try:
            send_edit_query(text)
        except KeyboardInterrupt:
            state.console.print("\n[yellow]Interrupted.[/yellow]")
        except Exception as e:
            state.console.print(f"[bold red]Error:[/bold red] {e}")

    @command("normal", "Confirm every destructive operation")
    def cmd_normal(self, parts):
        return self._set_llm_mode("normal", parts)

    @command("plan", "Read-only tools, no edits")
    def cmd_plan(self, parts):
        return self._set_llm_mode("plan", parts)

    @command("auto", "Auto-approve all tool calls")
    def cmd_auto(self, parts):
        return self._set_llm_mode("auto", parts)

    def _set_llm_mode(self, mode: str, parts):
        from ..settings import set as set_setting
        self.llm_mode = mode
        state.agent_sub_mode = mode
        set_setting("agent_sub_mode", mode)
        labels = {
            "normal": "Confirm every destructive operation",
            "plan": "Read-only tools, no edits",
            "auto": "Auto-approve all tool calls",
        }
        state.console.print(f"[bold cyan]{mode}[/bold cyan] [dim]-- {labels[mode]}[/dim]")
        return "continue"

    @command("compile", "Compile the selected graph")
    def cmd_compile(self, parts):
        import json as _json
        from ..agents import codegen, registry

        folder = registry.graph_dir(self.graph_id)
        def_path = folder / "definition.json"
        if not def_path.is_file():
            state.console.print(
                f"[yellow]No definition.json in {folder}.[/yellow]\n"
                "[dim]This looks like a hand-written graph -- edit `__init__.py` "
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
            init_path = codegen.write_compiled_graph(self.graph_id, definition, functions)
        except Exception as e:
            state.console.print(f"[bold red]Codegen failed:[/bold red] {e}")
            return "continue"

        state.console.print(
            f"[green]Regenerated {init_path}[/green]\n"
            "[dim]Restart langosh-server to apply.[/dim]"
        )
        return "continue"

    @command("test", "Stateless test run against the server")
    def cmd_test(self, parts):
        from .exec_ import _stateless_test
        return _stateless_test(self.graph_id, parts)

    @command("delete", "Delete the selected graph")
    def cmd_delete(self, parts):
        import shutil
        import subprocess
        import questionary
        from ..agents import registry
        from ..settings import get_agents_path

        confirm = questionary.confirm(
            f"Remove graph '{self.graph_id}' from langgraph.json and delete its folder?",
            default=False,
        ).ask()
        if not confirm:
            state.console.print("[dim]Cancelled.[/dim]")
            return "continue"

        removed_entry = registry.remove_graph(self.graph_id)
        folder = registry.graph_dir(self.graph_id)
        removed_folder = False
        if folder.exists():
            shutil.rmtree(folder)
            removed_folder = True

        if removed_entry or removed_folder:
            state.console.print(
                f"[green]Deleted {self.graph_id}.[/green] "
                f"[dim](langgraph.json: {'removed' if removed_entry else 'absent'}, "
                f"folder: {'removed' if removed_folder else 'absent'})[/dim]"
            )
            agents_path = str(get_agents_path())
            subprocess.run(["git", "add", "-A"], cwd=agents_path, capture_output=True)
            result = subprocess.run(
                ["git", "commit", "-m", f"Delete graph: {self.graph_id}"],
                cwd=agents_path, capture_output=True, text=True,
            )
            if result.returncode == 0:
                state.console.print(f"[dim]Committed: {result.stdout.strip().splitlines()[-1]}[/dim]")
                push = subprocess.run(["git", "push"], cwd=agents_path, capture_output=True, text=True)
                if push.returncode == 0:
                    state.console.print("[dim]Pushed to remote.[/dim]")
                else:
                    state.console.print(f"[yellow]Push failed:[/yellow] [dim]{push.stderr.strip()}[/dim]")
            else:
                state.console.print(f"[dim]{result.stdout.strip() or result.stderr.strip()}[/dim]")
            state.console.print("[dim]Restart langosh-server to drop the registered graph.[/dim]")
            # Pop back to dev mode since graph is deleted
            self._stack.pop()
        else:
            state.console.print(f"[red]Nothing found for graph: {self.graph_id}[/red]")
        return "continue"

    @command("preview", "Visualize the selected graph")
    def cmd_preview(self, parts):
        import json as _json
        from rich.syntax import Syntax
        from ..agents import registry

        folder = registry.graph_dir(self.graph_id)
        def_path = folder / "definition.json"
        if not def_path.is_file():
            state.console.print(f"[yellow]No definition.json in {folder}.[/yellow]")
            return "continue"

        try:
            definition = _json.loads(def_path.read_text())
        except Exception as e:
            state.console.print(f"[bold red]Error reading definition.json:[/bold red] {e}")
            return "continue"

        state.console.print(f"\n[bold]Graph: {self.graph_id}[/bold]\n")
        state.console.print(Syntax(_json.dumps(definition, indent=2), "json", theme="monokai"))
        return "continue"
