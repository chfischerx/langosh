"""Server mode — manage server connections, config, and API keys."""

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
            stype = "langosh" if info.get("langosh_server", True) else "langgraph"
            active_tag = " [active]" if sname == active else ""
            state.console.print(
                f"  {marker} [cyan]{sname}[/cyan] -- {info.get('url', '')} [{stype}]{active_tag}"
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
                title=f"{marker} {sname} -- {info.get('url', '')}",
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
        surl = questionary.text("Server URL:", default="http://localhost:8001").ask()
        if not surl:
            state.console.print("[dim]Cancelled.[/dim]")
            return "continue"
        skey = questionary.text("API key (optional):", default="").ask()
        is_langosh = questionary.confirm("Langosh server (has admin endpoints)?", default=True).ask()
        add_server(sname, surl.strip(), skey.strip() or None, is_langosh)
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
                title=f"{sname} -- {info.get('url', '')}",
                value=sname,
            ))

        picked = questionary.select("Update which server?", choices=choices).ask()
        if not picked:
            return "continue"

        info = servers[picked]
        new_url = questionary.text("URL:", default=info.get("url", "")).ask()
        if new_url is None:
            return "continue"
        new_key = questionary.text("API key:", default=info.get("api_key") or "").ask()
        if new_key is None:
            return "continue"
        cur_langosh = info.get("langosh_server", True)
        new_langosh = questionary.confirm("Langosh server?", default=cur_langosh).ask()

        update_server(picked, url=new_url.strip(), api_key=new_key.strip() or None, langosh_server=new_langosh)
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
        for sname in servers:
            label = f"{sname} (active)" if sname == active else sname
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
                stype = "langosh" if info.get("langosh_server", True) else "langgraph"
                active_tag = " [active]" if sname == active else ""
                state.console.print(
                    f"  {marker} [cyan]{sname}[/cyan] -- {info.get('url', '')} [{stype}]{active_tag}"
                )
        else:
            state.console.print("[dim]No servers configured. Use /add.[/dim]")
        state.console.print("[dim]Type /help for commands, /back to return.[/dim]")


class SelectedServerMode(_ServerCommandsMixin, Mode):
    """Selected server mode — all server commands plus info, reload, config, apikeys."""

    def __init__(self, server_name: str):
        self.server_name = server_name

    def path_label(self) -> str:
        return f"server[{self.server_name}]"

    _LANGOSH_ONLY = {"reload", "config", "apikeys"}

    def _is_langosh(self) -> bool:
        from ..settings import get_servers
        info = get_servers().get(self.server_name, {})
        return info.get("langosh_server", True)

    def get_menu(self) -> list[tuple[str, str]]:
        if self._is_langosh():
            return super().get_menu()
        return [(cmd, desc) for cmd, desc in super().get_menu()
                if cmd.lstrip("/") not in self._LANGOSH_ONLY]

    def handle_command(self, cmd_name: str, parts: list[str]) -> str:
        if cmd_name in self._LANGOSH_ONLY and not self._is_langosh():
            state.console.print("[dim]Not available — not a langosh server.[/dim]")
            return "continue"
        return super().handle_command(cmd_name, parts)

    def on_enter(self) -> None:
        from ..settings import get_servers
        info = get_servers().get(self.server_name, {})
        stype = "langosh" if info.get("langosh_server", True) else "langgraph"
        state.console.print(
            f"[bold cyan]Server: {self.server_name}[/bold cyan] "
            f"[dim]({info.get('url', '?')}, {stype})[/dim]"
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
                # Flatten nested dicts (e.g. flags, host)
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

    @command("reload", "Hot-reload agent repo (langosh server only)")
    def cmd_reload(self, parts):
        from ..settings import is_langosh_server
        from ..worker import run_in_background

        if not is_langosh_server():
            state.console.print("[dim]Not a langosh server -- reload not available.[/dim]")
            return "continue"

        def _work():
            from ..server import server_client
            result = asyncio.run(server_client.reload_agents())
            state.console.print("[green]Agents reloaded on server.[/green]")
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

        run_in_background("Reloading server...", _work)
        return "continue"

    @command("config", "Show and edit server config")
    def cmd_config(self, parts):
        from ..settings import is_langosh_server
        if not is_langosh_server():
            state.console.print("[dim]Not a langosh server -- config not available.[/dim]")
            return "continue"
        self._stack.push(ServerConfigMode(self.server_name))
        return "continue"

    @command("apikeys", "Show and edit API keys for CLI auth")
    def cmd_apikeys(self, parts):
        from ..settings import is_langosh_server
        if not is_langosh_server():
            state.console.print("[dim]Not a langosh server -- API keys not available.[/dim]")
            return "continue"
        self._stack.push(ServerApiKeysMode(self.server_name))
        return "continue"


class ServerConfigMode(Mode):
    """Server config mode — view and edit server configuration."""

    def __init__(self, server_name: str):
        self.server_name = server_name

    def path_label(self) -> str:
        return "config"

    def on_enter(self) -> None:
        state.console.print(f"[bold cyan]Server config[/bold cyan] [dim]({self.server_name})[/dim]")

    @command("show", "Show server configuration")
    def cmd_show(self, parts):
        from ..server import server_client

        try:
            schema = asyncio.run(server_client.get_config_schema())
            current = asyncio.run(server_client.list_config())
        except Exception as e:
            state.console.print(f"[bold red]Error:[/bold red] {e}")
            return "continue"

        current_by_key = {v["key"]: v.get("value", "") for v in current}
        current_cat = ""
        for s in schema:
            if s["category"] != current_cat:
                current_cat = s["category"]
                state.console.print(f"\n  [bold]{current_cat}[/bold]")
            key = s["key"]
            val = current_by_key.get(key)
            if val is None:
                state.console.print(f"    [cyan]{key}[/cyan] [dim][not set][/dim]")
            elif s.get("encrypted") and val:
                state.console.print(f"    [cyan]{key}[/cyan] = {val[:4]}...")
            else:
                state.console.print(f"    [cyan]{key}[/cyan] = {val}")
        state.console.print()
        return "continue"

    @command("reset", "Reset entire server configuration")
    def cmd_reset(self, parts):
        import questionary
        from ..server import server_client

        confirm = questionary.confirm(
            "Reset all config? Values revert to env-var fallbacks.", default=False
        ).ask()
        if confirm:
            try:
                asyncio.run(server_client.reset_config())
                state.console.print("[green]All config values reset.[/green]")
            except Exception as e:
                state.console.print(f"[bold red]Error:[/bold red] {e}")
        return "continue"

    @command("configure", "Configure server config step by step")
    def cmd_configure(self, parts):
        import questionary
        from ..server import server_client

        try:
            schema = asyncio.run(server_client.get_config_schema())
            current = asyncio.run(server_client.list_config())
        except Exception as e:
            state.console.print(f"[bold red]Error:[/bold red] {e}")
            return "continue"

        current_by_key = {v["key"]: v.get("value", "") for v in current}
        categories: dict[str, list[dict]] = {}
        for s in schema:
            categories.setdefault(s["category"], []).append(s)

        changed = 0
        for cat, params in categories.items():
            state.console.print(f"\n[bold]{cat}[/bold]")
            for s in params:
                key = s["key"]
                cur_val = current_by_key.get(key)
                encrypted = s.get("encrypted", False)
                if cur_val is not None and encrypted:
                    disp = f"{cur_val[:4]}..."
                elif cur_val is not None:
                    disp = cur_val
                else:
                    disp = "[not set]"
                state.console.print(f"  [cyan]{key}[/cyan] = {disp}")
                state.console.print(f"  [dim]{s['description']}[/dim]")
                if encrypted:
                    value = questionary.password(f"  {key} (Enter to skip):").ask()
                else:
                    value = questionary.text(f"  {key}:", default=cur_val or "").ask()
                if value is None:
                    state.console.print("[dim]Wizard cancelled.[/dim]")
                    break
                value = value.strip()
                if not value and cur_val is None:
                    continue
                if not value and cur_val is not None:
                    try:
                        asyncio.run(server_client.delete_config(cat, key))
                        current_by_key.pop(key, None)
                        changed += 1
                        state.console.print("  [green]Cleared.[/green]")
                    except Exception as e:
                        state.console.print(f"  [bold red]Error:[/bold red] {e}")
                    continue
                if value == cur_val:
                    continue
                try:
                    asyncio.run(server_client.set_config(cat, key, value))
                    current_by_key[key] = value
                    changed += 1
                    state.console.print("  [green]Set.[/green]")
                except Exception as e:
                    state.console.print(f"  [bold red]Error:[/bold red] {e}")

        state.console.print(f"\n[green]Done.[/green] [dim]{changed} value(s) changed.[/dim]")
        return "continue"


class ServerApiKeysMode(Mode):
    """Server API keys mode — list, create, delete, rotate API keys."""

    def __init__(self, server_name: str):
        self.server_name = server_name

    def path_label(self) -> str:
        return "apikeys"

    def on_enter(self) -> None:
        state.console.print(f"[bold cyan]API keys[/bold cyan] [dim]({self.server_name})[/dim]")

    @command("list", "List all API keys")
    def cmd_list(self, parts):
        from ..server import server_client

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
                state.console.print(f"  [cyan]{name}[/cyan] \u2014 {short_key} [dim]({created})[/dim]")
        return "continue"

    @command("create", "Create an API key")
    def cmd_create(self, parts):
        import questionary
        from ..server import server_client

        name = questionary.text("Key name:").ask()
        if not name or not name.strip():
            state.console.print("[dim]Cancelled.[/dim]")
            return "continue"
        try:
            result = asyncio.run(server_client.create_api_key(name.strip()))
            key_val = result.get("key") or result.get("api_key") or str(result)
            state.console.print(f"[green]Created API key '{name.strip()}':[/green]")
            state.console.print(f"  [bold]{key_val}[/bold]")
            state.console.print("[dim]Save this key -- it won't be shown again.[/dim]")
        except Exception as e:
            state.console.print(f"[bold red]Error:[/bold red] {e}")
        return "continue"

    @command("delete", "Delete an API key")
    def cmd_delete(self, parts):
        import questionary
        from ..server import server_client

        name = questionary.text("Key name to delete:").ask()
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
        return "continue"

    @command("rotate", "Rotate an API key")
    def cmd_rotate(self, parts):
        import questionary
        from ..server import server_client

        name = questionary.text("Key name to rotate:").ask()
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
                state.console.print("[dim]Save this key -- the old one is now invalid.[/dim]")
            except Exception as e:
                state.console.print(f"[bold red]Error:[/bold red] {e}")
        return "continue"
