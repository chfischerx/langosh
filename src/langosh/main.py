"""CLI entry point."""

import os

# Disable prompt_toolkit's cursor-position-request (CPR) probing. We call
# `Application.run()` from a worker thread inside `asyncio.to_thread` to
# show tool-approval widgets during edit loops; on terminals that don't
# respond to CPR (notably some split-pane / tmux / IDE terminals), the
# pending CPR futures outlive their event loop and later crash the main
# REPL with "Future attached to a different loop". Disabling CPR makes
# the renderer skip the probe entirely — nothing else depends on it.
os.environ.setdefault("PROMPT_TOOLKIT_NO_CPR", "1")

import typer  # noqa: E402

from .commands.typer_cmds import register  # noqa: E402
from .repl import load_models, repl  # noqa: E402

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
