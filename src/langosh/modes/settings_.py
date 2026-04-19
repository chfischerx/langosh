"""Settings mode — view and edit CLI-side settings."""

import langosh.state as state

from . import Mode, command


class SettingsMode(Mode):
    """Settings mode — manage local CLI settings."""

    def path_label(self) -> str:
        return "settings"

    def on_enter(self) -> None:
        state.console.print("[bold cyan]Settings mode.[/bold cyan]")
        state.console.print("[dim]Type /help for commands, /back to return.[/dim]")

    @command("show", "Show all settings")
    def cmd_show(self, parts):
        from ..settings import get as get_setting, get_active_server_name, get_servers

        _SETTINGS_SCHEMA = [
            ("anthropic_api_key", "Anthropic API key", "", "str"),
            ("openai_api_key", "OpenAI API key", "", "str"),
            ("default_provider", "Default LLM provider", "anthropic", "str"),
            ("default_model", "Default model ID", "", "str"),
            ("aws_bedrock_region", "AWS Bedrock region", "us-east-1", "str"),
            ("max_tokens", "Max tokens per response", "4096", "int"),
            ("max_tool_turns", "Max tool call rounds", "10", "int"),
        ]

        # Show servers
        servers = get_servers()
        active = get_active_server_name()
        state.console.print("\n  [bold]Servers[/bold]")
        if servers:
            for sname, info in servers.items():
                marker = "\u25cf" if sname == active else "\u25cb"
                state.console.print(
                    f"    {marker} [cyan]{sname}[/cyan] -- {info.get('url', '')}"
                )
        else:
            state.console.print("    [dim]none configured[/dim]")

        # Show other settings
        state.console.print("\n  [bold]Settings[/bold]")
        for key, label, default, _ in _SETTINGS_SCHEMA:
            val = get_setting(key)
            if val is not None:
                disp = str(val)
            else:
                disp = f"[default: {default}]" if default else "[not set]"
            state.console.print(f"    {label:30} {disp}")
        state.console.print()
        return "continue"

    @command("configure", "Update settings interactively")
    def cmd_configure(self, parts):
        import questionary
        from ..settings import get as get_setting, set as set_setting, delete as del_setting

        _SETTINGS_SCHEMA = [
            ("anthropic_api_key", "Anthropic API key", "", "str"),
            ("openai_api_key", "OpenAI API key", "", "str"),
            ("default_provider", "Default LLM provider", "anthropic", "str"),
            ("default_model", "Default model ID", "", "str"),
            ("aws_bedrock_region", "AWS Bedrock region", "us-east-1", "str"),
            ("max_tokens", "Max tokens per response", "4096", "int"),
            ("max_tool_turns", "Max tool call rounds", "10", "int"),
        ]

        while True:
            choices = [questionary.Choice(title="\u2190 Back", value=None)]
            for key, label, default, _ in _SETTINGS_SCHEMA:
                val = get_setting(key)
                if val is not None:
                    disp = str(val)
                else:
                    disp = f"[default: {default}]" if default else "[not set]"
                choices.append(questionary.Choice(
                    title=f"{label:30} {disp}",
                    value=key,
                ))

            picked = questionary.select("Setting:", choices=choices).ask()
            if not picked:
                return "continue"

            schema = next(s for s in _SETTINGS_SCHEMA if s[0] == picked)
            key, label, default, stype = schema
            cur = get_setting(key)

            state.console.print(f"  [dim]{label}[/dim]")

            actions = ["Set value"]
            if cur is not None:
                actions.append("Clear (revert to default)")
            actions.append("\u2190 Back")
            action = questionary.select("Action:", choices=actions).ask()

            if not action or action.startswith("\u2190"):
                continue

            if action.startswith("Clear"):
                del_setting(key)
                state.console.print(f"[green]Cleared {key}.[/green]")
                continue

            prompt_default = str(cur) if cur is not None else default
            value = questionary.text(f"{key}:", default=prompt_default).ask()
            if value is None:
                continue
            value = value.strip()
            if not value:
                continue

            if stype == "int":
                try:
                    set_setting(key, int(value))
                except ValueError:
                    state.console.print("[bold red]Must be a number.[/bold red]")
                    continue
            else:
                set_setting(key, value)
            state.console.print(f"[green]Set {key}.[/green]")

        return "continue"
