"""Tests for the build-time tool-catalog fetcher."""

from __future__ import annotations

import pytest

pytest.importorskip("langchain_community.tools")

from langosh.graphs import tool_discovery, tool_fetcher  # noqa: E402
from langosh.graphs.tool_cache import read_cache  # noqa: E402


def _stub_discover(entries):
    """Return a no-arg function that mimics `discover_tools()` output."""
    def _fn():
        return list(entries)
    return _fn


@pytest.fixture
def stubbed_discovery(monkeypatch):
    """Replace `tool_discovery.discover_tools` with a controllable stub."""
    def _install(entries):
        monkeypatch.setattr(tool_discovery, "discover_tools", _stub_discover(entries))
    return _install


class TestFetchCatalog:
    def test_writes_cache_file(self, agents_path, stubbed_discovery) -> None:
        stubbed_discovery([
            {
                "name": "dummy",
                "source": "community:dummy.tool",
                "description": "A dummy.",
                "parameters": [],
                "imports": ["from x import Dummy"],
                "ctor": "Dummy()",
            },
        ])
        summary = tool_fetcher.fetch_catalog()
        assert summary["total"] == 1
        # Catalog persists to the per-agents-path cache.
        cached = read_cache(agents_path)
        assert cached is not None
        assert cached[0]["name"] == "dummy"

    def test_summary_groups_by_source_prefix(self, stubbed_discovery, agents_path) -> None:
        stubbed_discovery([
            _entry("a", "community:a.tool"),
            _entry("b", "community:b.tool"),
            _entry("c", "experimental:python.tool"),
        ])
        summary = tool_fetcher.fetch_catalog()
        assert set(summary["by_source"].keys()) == {"community", "experimental"}
        assert set(summary["by_source"]["community"]) == {"a", "b"}
        assert summary["by_source"]["experimental"] == ["c"]

    def test_empty_catalog_when_discovery_raises(
        self, stubbed_discovery, agents_path, monkeypatch
    ) -> None:
        def _raises():
            raise RuntimeError("boom")
        monkeypatch.setattr(tool_discovery, "discover_tools", _raises)
        summary = tool_fetcher.fetch_catalog()
        assert summary["total"] == 0

    def test_cache_is_per_agents_path(self, agents_path, stubbed_discovery) -> None:
        stubbed_discovery([_entry("tool_one", "community:one.tool")])
        tool_fetcher.fetch_catalog()
        cached = read_cache(agents_path)
        assert cached and cached[0]["name"] == "tool_one"


def _entry(name: str, source: str) -> dict:
    """Minimal well-formed catalog entry."""
    return {
        "name": name,
        "source": source,
        "description": "x",
        "parameters": [],
        "imports": ["from pkg import Cls"],
        "ctor": "Cls()",
    }
