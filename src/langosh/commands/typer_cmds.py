"""Typer CLI commands (version, models, model, search, ask)."""

import typer

import langosh.state as state

from ..input import model_display_name


def register(app: typer.Typer) -> None:
    """Register all typer commands on the app."""

    @app.command()
    def version() -> None:
        """Show the application version."""
        from importlib.metadata import version as get_version

        try:
            v = get_version("langosh")
        except Exception:
            v = "0.1.0 (dev)"
        state.console.print(f"langosh [bold cyan]{v}[/bold cyan]")

    @app.command()
    def models(
        query: str = typer.Argument(None, help="Provider name or search term to filter models"),
    ) -> None:
        """List available LLM providers and models. Use '/model <number>' to select."""
        from rich.table import Table

        if not state.model_cache:
            state.console.print("[yellow]No models found.[/yellow] Check that API keys are configured in /admin /settings")
            return

        if query and query in state.model_cache:
            fetched = {query: state.model_cache[query]}
        elif query:
            query_lower = query.lower()
            fetched: dict = {}
            for prov, mlist in state.model_cache.items():
                matches = [m for m in mlist if query_lower in m.id.lower() or query_lower in m.name.lower()]
                if matches:
                    fetched[prov] = matches
            if not fetched:
                search(query)
                return
        else:
            fetched = state.model_cache

        state.last_results.clear()
        for prov in sorted(fetched):
            state.last_results.extend(fetched[prov])

        table = Table(show_header=True, header_style="bold", padding=(0, 1))
        table.add_column("#", justify="right", style="dim")
        table.add_column("Provider")
        table.add_column("Name")
        table.add_column("Model ID", style="dim")

        active_prov = state.active_model["provider"]
        active_id = state.active_model["model_id"]

        num = 0
        for prov in sorted(fetched):
            first = True
            for m in fetched[prov]:
                num += 1
                prov_cell = f"[bold]{prov}[/bold]" if first else ""
                is_active = m.provider == active_prov and m.id == active_id
                name = f"[green]{m.name} *[/green]" if is_active else m.name
                table.add_row(str(num), prov_cell, name, m.id)
                first = False

        state.console.print(table)
        if active_prov and active_id:
            state.console.print(f"[dim]Active: {active_prov}:{active_id}[/dim]")

    @app.command()
    def model(
        selection: str = typer.Argument(..., help="Model number from 'models' list, or provider:model_id"),
    ) -> None:
        """Select a model for subsequent LLM calls."""
        from ..settings import set as set_setting

        if selection.isdigit():
            source = state.last_results if state.last_results else state.model_list
            idx = int(selection) - 1
            if idx < 0 or idx >= len(source):
                state.console.print(f"[bold red]Invalid number.[/bold red] Use 1-{len(source)}")
                return
            m = source[idx]
            state.active_model["provider"] = m.provider
            state.active_model["model_id"] = m.id
            set_setting("active_model", {"provider": m.provider, "model_id": m.id})
            state.console.print(f"Active model: [bold]{m.provider}[/bold] / [cyan]{m.id}[/cyan] ({m.name})")
            return

        if ":" in selection:
            prov, model_id = selection.split(":", 1)
            state.active_model["provider"] = prov
            state.active_model["model_id"] = model_id
            set_setting("active_model", {"provider": prov, "model_id": model_id})
            state.console.print(f"Active model: [bold]{prov}[/bold] / [cyan]{model_id}[/cyan]")
            return

        state.console.print("[bold red]Usage:[/bold red] /model <number> or /model <provider:model_id>")

    @app.command()
    def search(
        query: str = typer.Argument(..., help="Search term (fuzzy matched against model ID and name)"),
    ) -> None:
        """Search for models by name or ID. Use '/model <number>' to select a result."""
        from difflib import SequenceMatcher

        from rich.table import Table

        if not state.model_list:
            state.console.print("[yellow]No models loaded.[/yellow]")
            return

        query_lower = query.lower()

        scored: list[tuple[float, object]] = []
        for m in state.model_list:
            id_lower = m.id.lower()
            name_lower = m.name.lower()

            if query_lower in id_lower or query_lower in name_lower:
                score = 1.0
            else:
                score = max(
                    SequenceMatcher(None, query_lower, id_lower).ratio(),
                    SequenceMatcher(None, query_lower, name_lower).ratio(),
                    *(
                        SequenceMatcher(None, word, id_lower).ratio()
                        for word in query_lower.split()
                    ),
                    *(
                        SequenceMatcher(None, word, name_lower).ratio()
                        for word in query_lower.split()
                    ),
                )
            scored.append((score, m))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = [(s, m) for s, m in scored if s > 0.3][:15]

        if not top:
            state.console.print(f"[yellow]No models matching:[/yellow] {query}")
            return

        state.last_results.clear()
        for _, m in top:
            state.last_results.append(m)

        table = Table(show_header=True, header_style="bold", padding=(0, 1))
        table.add_column("#", justify="right", style="dim")
        table.add_column("Provider")
        table.add_column("Name")
        table.add_column("Model ID", style="dim")
        table.add_column("Score", justify="right", style="dim")

        for num, (score, m) in enumerate(top, 1):
            table.add_row(str(num), m.provider, m.name, m.id, f"{score:.0%}")

        state.console.print(table)

    @app.command()
    def ask(
        prompt: str = typer.Argument(..., help="Prompt to send to the LLM"),
        provider: str = typer.Option(None, "--provider", "-p", help="LLM provider"),
        model: str = typer.Option(None, "--model", "-m", help="Model ID"),
    ) -> None:
        """Send a one-shot prompt to an LLM provider."""
        import asyncio
        import time

        from ..config import DEFAULT_MODELS, get_settings
        from ..llm import call_llm_simple
        from ..llm.prompts.chat import CHAT_SYSTEM_PROMPT
        from ..rendering import print_renderables, render_semantic
        from ..queries import format_elapsed

        settings = get_settings()
        provider = provider or state.active_model["provider"] or settings.default_provider
        model = model or state.active_model["model_id"] or settings.default_model or DEFAULT_MODELS.get(provider, "")

        start = time.monotonic()
        with state.console.status(f"[dim]Calling {model_display_name() or model}...[/dim]"):
            result = asyncio.run(
                call_llm_simple(
                    provider=provider,
                    model_id=model,
                    api_key=None,
                    system=CHAT_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": prompt}],
                )
            )
        elapsed = time.monotonic() - start

        print_renderables(state.console, render_semantic(result["text"]))
        state.console.print(
            f"\n[dim]{format_elapsed(elapsed)} | "
            f"{result['input_tokens']} ↑ / {result['output_tokens']} ↓[/dim]"
        )
