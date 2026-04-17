"""Root mode — entry point, mode switches only."""

from . import Mode, command


class MainMode(Mode):

    def path_label(self) -> str:
        import langosh.state as state
        server = state.active_server_name
        return f"main[{server}]" if server else "main"

    @command("dev", "Graph development mode")
    def cmd_dev(self, parts):
        from .dev import DevMode
        self._stack.push(DevMode())
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

    @command("llm", "LLM chat and code mode")
    def cmd_llm(self, parts):
        from .llm import LlmMode
        self._stack.push(LlmMode())
        return "continue"

    @command("server", "Server management")
    def cmd_server(self, parts):
        import langosh.state as st
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
