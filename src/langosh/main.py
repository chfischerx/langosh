"""CLI entry point."""

import typer

from .commands.typer_cmds import register
from .repl import load_models, repl

app = typer.Typer(
    name="langosh",
    help="A CLI tool built with Typer and Rich.",
    invoke_without_command=True,
)

# Register all typer commands (hello, version, models, use, search, ask)
register(app)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """A CLI tool built with Typer and Rich."""
    load_models()
    if ctx.invoked_subcommand is None:
        repl(app)


if __name__ == "__main__":
    app()
