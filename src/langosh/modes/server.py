"""Server mode — manage LangGraph Platform / LangSmith server connections."""

import asyncio

import langosh.state as state

from . import Mode, command


class _ServerCommandsMixin:
    """Shared server CRUD commands for both ServerMode and SelectedServerMode."""

    @command("list", "List all configured servers")
    def cmd_list(self, parts):
        from ..settings import get_active_server_name, get_servers
        servers = get_servers()
        active = get_active_server_name()
        if not servers:
            state.console.print("[dim]No servers configured. Use /add to add one.[/dim]")
            return "continue"
        for sname, info in servers.items():
            marker = "\u25cf" if sname == active else "\u25cb"
            active_tag = " [active]" if sname == active else ""
            state.console.print(
                f"  {marker} [cyan]{sname}[/cyan] \u2014 {info.get('url', '')}{active_tag}"
            )
        return "continue"

    @command("select", "Select a server")
    def cmd_select(self, parts):
        import questionary
        from ..settings import get_active_server_name, get_servers, set_active_server

        servers = get_servers()
        if not servers:
            state.console.print("[dim]No servers configured. Use /add first.[/dim]")
            return "continue"

        choices = [questionary.Choice(title="\u2190 Back", value=None)]
        active = get_active_server_name()
        for sname, info in servers.items():
            marker = "\u25cf" if sname == active else "\u25cb"
            choices.append(questionary.Choice(
                title=f"{marker} {sname} \u2014 {info.get('url', '')}",
                value=sname,
            ))

        picked = questionary.select("Server:", choices=choices).ask()
        if not picked:
            return "continue"

        set_active_server(picked)
        state.active_server_name = picked
        if hasattr(self, "server_name"):
            self.server_name = picked
        state.console.print(f"[green]Selected server '{picked}'.[/green]")
        return "continue"

    @command("add", "Add a server")
    def cmd_add(self, parts):
        import questionary
        from ..settings import add_server

        sname = questionary.text("Server name:").ask()
        if not sname or not sname.strip():
            state.console.print("[dim]Cancelled.[/dim]")
            return "continue"
        sname = sname.strip()
        surl = questionary.text("Server URL:", default="http://localhost:2024").ask()
        if not surl:
            state.console.print("[dim]Cancelled.[/dim]")
            return "continue"
        add_server(sname, surl.strip())
        state.active_server_name = state.active_server_name or sname
        state.console.print(f"[green]Added server '{sname}'.[/green]")
        return "continue"

    @command("update", "Update a server")
    def cmd_update(self, parts):
        import questionary
        from ..settings import get_servers, update_server

        servers = get_servers()
        if not servers:
            state.console.print("[dim]No servers configured.[/dim]")
            return "continue"

        choices = [questionary.Choice(title="\u2190 Back", value=None)]
        for sname, info in servers.items():
            choices.append(questionary.Choice(
                title=f"{sname} \u2014 {info.get('url', '')}",
                value=sname,
            ))

        picked = questionary.select("Update which server?", choices=choices).ask()
        if not picked:
            return "continue"

        info = servers[picked]
        new_url = questionary.text("URL:", default=info.get("url", "")).ask()
        if new_url is None:
            return "continue"

        update_server(picked, url=new_url.strip())
        state.console.print(f"[green]Updated server '{picked}'.[/green]")
        return "continue"

    @command("delete", "Delete a server")
    def cmd_delete(self, parts):
        import questionary
        from ..settings import get_active_server_name, get_servers, remove_server

        servers = get_servers()
        if not servers:
            state.console.print("[dim]No servers configured.[/dim]")
            return "continue"

        active = get_active_server_name()
        choices = [questionary.Choice(title="\u2190 Back", value=None)]
        for sname, spec in servers.items():
            url = spec.get("url", "")
            suffix = " (active)" if sname == active else ""
            label = f"{sname} \u2014 {url}{suffix}"
            choices.append(questionary.Choice(title=label, value=sname))

        picked = questionary.select("Delete which server?", choices=choices).ask()
        if not picked:
            return "continue"

        if picked == active:
            state.console.print("[red]Cannot delete the active server. Switch first.[/red]")
            return "continue"

        confirm = questionary.confirm(f"Delete server '{picked}'?", default=False).ask()
        if confirm:
            remove_server(picked)
            state.console.print(f"[green]Deleted server '{picked}'.[/green]")
        return "continue"


class ServerMode(_ServerCommandsMixin, Mode):
    """Server mode — no server selected yet."""

    def path_label(self) -> str:
        return "server"

    def on_enter(self) -> None:
        from ..settings import get_active_server_name, get_servers
        servers = get_servers()
        active = get_active_server_name()

        state.console.print("[bold cyan]Server mode.[/bold cyan]")
        if servers:
            for sname, info in servers.items():
                marker = "\u25cf" if sname == active else "\u25cb"
                active_tag = " [active]" if sname == active else ""
                state.console.print(
                    f"  {marker} [cyan]{sname}[/cyan] \u2014 {info.get('url', '')}{active_tag}"
                )
        else:
            state.console.print("[dim]No servers configured. Use /add.[/dim]")
        state.console.print("[dim]Type /help for commands, /back to return.[/dim]")


class SelectedServerMode(_ServerCommandsMixin, Mode):
    """Selected server mode — CRUD commands plus /info."""

    def __init__(self, server_name: str):
        self.server_name = server_name

    def path_label(self) -> str:
        return f"server[{self.server_name}]"

    def on_enter(self) -> None:
        from ..settings import get_servers
        info = get_servers().get(self.server_name, {})
        state.console.print(
            f"[bold cyan]Server: {self.server_name}[/bold cyan] "
            f"[dim]({info.get('url', '?')})[/dim]"
        )

    @command("info", "Server version, graphs, status")
    def cmd_info(self, parts):
        from rich.table import Table
        from ..server import server_client

        try:
            info = asyncio.run(server_client.server_info())
        except Exception as e:
            state.console.print(f"[bold red]Server error:[/bold red] {e}")
            return "continue"

        table = Table(show_header=False, padding=(0, 2), box=None)
        table.add_column(style="bold")
        table.add_column()

        for key, value in info.items():
            if isinstance(value, dict):
                items = ", ".join(
                    f"{k}={v}" for k, v in value.items() if v is not None
                )
                table.add_row(key, items or "--")
            elif isinstance(value, list):
                table.add_row(key, ", ".join(str(v) for v in value) or "--")
            else:
                table.add_row(key, str(value) if value is not None else "--")

        state.console.print(table)
        return "continue"
