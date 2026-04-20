# Contributing to Langosh

Thanks for taking the time to look. Langosh is early, moving fast,
and happy to have contributors who want to help shape it.

## Dev setup

Prereqs: **Python 3.11+** and either `uv` (recommended) or plain
`pip`/`venv`.

```sh
# clone
git clone https://github.com/chfischerx/langosh.git
cd langosh

# editable install with uv
uv sync
uv run langosh version

# or with pip
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
langosh version
```

## Running checks locally

Before opening a PR, run the same checks CI runs:

```sh
# lint — must be clean (CI hard-fails on any ruff error)
ruff check src/

# tests — the suite lives under tests/ (when present)
pytest -q

# smoke test the CLI
langosh version
```

## Code style

- **Formatting / lint** — `ruff` with the config in
  [`pyproject.toml`](pyproject.toml) (`line-length = 120`, `select =
  ["E", "F", "I", "N", "W"]`). Run `ruff check --fix src/` to
  auto-apply the safe subset.
- **Imports** — `ruff`'s `I` rules (isort layout) handle ordering;
  don't reorder manually.
- **Typing** — not enforced by CI yet, but match the surrounding
  code. Public functions prefer `str | None` unions over `Optional`.
- **Docstrings** — one-liners on module-level functions; longer
  prose for non-obvious behavior (why, not what).

## PR process

1. **One change per PR.** Small, focused PRs land fast. Big ones
   stall.
2. **Branch off `main`, rebase if it falls behind.**
3. **CI must be green** — `CI` and `Publish` workflow badges on the
   PR. Lint failures are blocking.
4. **PR title** — short, imperative mood ("Add stream_mode picker",
   not "Added picker"). The commit log is going to end up as the
   release notes.
5. **PR body** — use the [template](.github/PULL_REQUEST_TEMPLATE.md)
   GitHub pre-fills. Motivation and testing notes matter more than
   length.
6. **Docs stay current.** If you change a CLI command, update
   [`README.md`](README.md). If you touch the LangGraph client
   surface, update [`docs/langgraph_api.md`](docs/langgraph_api.md).
7. **Review** — the maintainer will read it. Expect comments.
   `force-push` on your branch is fine; we squash-merge.

## Filing issues

- **Bug:** use the [Bug Report](https://github.com/chfischerx/langosh/issues/new/choose)
  template. Include `langosh version`, Python version, OS, and a
  minimal repro.
- **Feature:** use the Feature Request template. Lead with the
  problem you're hitting, not the implementation.
- **Docs:** use the Docs Improvement template.
- **Security:** **do not open a public issue** — see
  [SECURITY.md](SECURITY.md).

## Reviewing the code before your first PR

Worth skimming:

- [`src/langosh/main.py`](src/langosh/main.py) — Typer entry point.
- [`src/langosh/repl.py`](src/langosh/repl.py) — the interactive
  loop, history / tool-cache loading, mode stack wiring.
- [`src/langosh/modes/`](src/langosh/modes/) — one file per mode
  (main, dev, exec_, server, llm, settings_). Commands live here.
- [`src/langosh/graphs/codegen.py`](src/langosh/graphs/codegen.py)
  — `definition.json` → Python module compiler.
- [`src/langosh/graphs/tool_discovery.py`](src/langosh/graphs/tool_discovery.py)
  — build-time tool catalog walker.

The test suite, when present, lives under `tests/`.

## License

By submitting a change, you agree it's covered by the
[MIT license](LICENSE) that already applies to the project.
