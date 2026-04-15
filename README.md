# langosh

A CLI tool built with [Typer](https://typer.tiangolo.com/) and [Rich](https://rich.readthedocs.io/).

## Requirements

- Python 3.11+

## Installation

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Usage

```sh
langosh --help
```

### Commands

#### `hello`

Greet someone with style.

```sh
langosh hello              # Hello, World!
langosh hello Claude       # Hello, Claude!
langosh hello Claude -c 3  # greet 3 times
```

#### `version`

Show the application version.

```sh
langosh version
```

## Development

```sh
source .venv/bin/activate
pip install -e .
```

## Project Structure

```
src/
  langosh/
    __init__.py
    main.py          # CLI entrypoint and commands
pyproject.toml       # Project metadata and dependencies
```

## Adding Commands

Define new commands in `src/langosh/main.py`:

```python
@app.command()
def my_command(arg: str = typer.Argument(..., help="Description")) -> None:
    """Command docstring shown in --help."""
    console.print(f"[bold]{arg}[/bold]")
```

For command groups, create a sub-app with `typer.Typer()` and register it via `app.add_typer()`.

## License

MIT
