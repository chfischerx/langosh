"""Shared pytest fixtures for the Langosh test suite."""

from __future__ import annotations

import pathlib
import sys

import pytest

# Make `langosh` importable from src/ without an editable install
# (keeps `pytest` working in bare venvs).
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))


class _SilentConsole:
    """Stand-in for rich.Console that swallows output during tests."""

    def print(self, *args, **kwargs) -> None:  # noqa: D401, ARG002
        return None


@pytest.fixture(autouse=True)
def silence_console(monkeypatch):
    """Replace the global rich Console so production `state.console.print`
    calls don't pollute test output."""
    import langosh.state as state
    monkeypatch.setattr(state, "console", _SilentConsole())


@pytest.fixture
def agents_path(tmp_path, monkeypatch):
    """Point Langosh's `get_agents_path()` resolver at a tmpdir via env var.

    Uses `LANGOSH_AGENTS_PATH` since that's checked first in the
    resolver and doesn't suffer from the `from ..settings import
    get_agents_path` aliasing that a direct monkeypatch would.
    Returns the `Path` so tests can create / inspect files inside.
    """
    resolved = tmp_path.resolve()
    monkeypatch.setenv("LANGOSH_AGENTS_PATH", str(resolved))
    return resolved


@pytest.fixture
def tool_catalog(agents_path):
    """Populate the per-agents-path tool cache so codegen can resolve
    tools like `duckduckgo_search` in tests that reference them."""
    from langosh.graphs.tool_fetcher import fetch_catalog
    fetch_catalog()
    return agents_path
