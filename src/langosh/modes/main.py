"""Root mode — entry point, mode switches only."""

from . import Mode, command
from .dev import _GitMixin


class MainMode(_GitMixin, Mode):

    def path_label(self) -> str:
        import langosh.state as state
        server = state.active_server_name
        return f"main[{server}]" if server else "main"

    @command("graphs", "Graph development mode")
    def cmd_graphs(self, parts):
        from .dev import DevMode
        self._stack.push(DevMode())
        return "continue"

    @command("initrepo", "Scaffold a minimal langgraph-agents repo in the current directory")
    def cmd_initrepo(self, parts):
        import os
        from pathlib import Path

        import questionary

        import langosh.state as state

        from ..init_repo import init_repo

        cwd = Path(os.getcwd())
        default_name = cwd.name.replace(" ", "-").lower() or "agents"

        name = questionary.text(
            "Project name:",
            default=default_name,
            validate=lambda t: True if t.strip() else "Name cannot be empty",
        ).ask()
        if not name:
            state.console.print("[dim]Cancelled.[/dim]")
            return "continue"

        description = questionary.text(
            "Description:",
            default="LangGraph agents (Langosh-compatible).",
            validate=lambda t: True if t.strip() else "Description cannot be empty",
        ).ask()
        if not description:
            state.console.print("[dim]Cancelled.[/dim]")
            return "continue"

        from ..model_picker import LANGCHAIN_EXCLUDE, pick_model
        model = pick_model(
            "Default model for the example graph:",
            include_server_default=False,
            exclude_providers=LANGCHAIN_EXCLUDE,
        )
        if not model:
            state.console.print("[dim]Cancelled.[/dim]")
            return "continue"

        try:
            init_repo(
                cwd,
                name=name.strip(),
                description=description.strip(),
                default_model=model.strip(),
            )
        except Exception as e:
            state.console.print(f"[bold red]Error:[/bold red] {e}")
        return "continue"

    @command("fetchtools", "Refresh the tool catalog from LangChain community + experimental")
    def cmd_fetchtools(self, parts):
        _do_fetchtools()
        return "continue"

    @command("exec", "Execute graphs and assistants")
    def cmd_exec(self, parts):
        import langosh.state as state

        from ..settings import get_active_server_name

        server_name = get_active_server_name()
        if not server_name:
            state.console.print("[red]No server selected. Use /server first.[/red]")
            return "continue"

        from .exec_ import ExecMode
        self._stack.push(ExecMode(server_name))
        return "continue"

    @command("chat", "Chat with LLM")
    def cmd_chat(self, parts):
        from .llm import ChatMode
        self._stack.push(ChatMode())
        return "continue"

    @command("code", "LLM with tool use")
    def cmd_code(self, parts):
        from .llm import CodeMode
        self._stack.push(CodeMode())
        return "continue"

    @command("server", "Server management")
    def cmd_server(self, parts):
        from ..settings import get_active_server_name, get_servers

        active = get_active_server_name()
        servers = get_servers()

        if active and active in servers:
            from .server import SelectedServerMode
            self._stack.push(SelectedServerMode(active))
        else:
            from .server import ServerMode
            self._stack.push(ServerMode())
        return "continue"

    @command("settings", "CLI settings")
    def cmd_settings(self, parts):
        from .settings_ import SettingsMode
        self._stack.push(SettingsMode())
        return "continue"

    @command("version", "Show the application version")
    def cmd_version(self, parts):
        return "dispatch"


def _do_fetchtools() -> None:
    """Shared /fetchtools implementation. Introspects LangChain community +
    experimental tool packages, writes the per-agents-repo cache, prints
    a summary."""
    import langosh.state as state

    from ..graphs.tool_fetcher import fetch_catalog
    try:
        summary = fetch_catalog()
    except Exception as e:
        state.console.print(f"[bold red]Error fetching tools:[/bold red] {e}")
        return
    state.console.print(
        f"[green]Refreshed tool catalog[/green] [dim]({summary['agents_path']})[/dim]"
    )
    for source, names in sorted(summary["by_source"].items()):
        state.console.print(
            f"  [cyan]{source}[/cyan]  [dim]{len(names)} tools[/dim]"
        )
    state.console.print(f"[bold]Total:[/bold] {summary['total']} tools")
