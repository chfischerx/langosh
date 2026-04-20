"""Tests for build-time tool discovery + the override table."""

from __future__ import annotations

import pytest

from langosh.graphs.tool_discovery import (
    _CTOR_TRIM_SUFFIXES,
    _OVERRIDES,
    _find_utility,
    discover_tools,
)

# Skip the whole module when langchain-community isn't installed — the
# discovery walker requires it, and the CLI ships with it as a hard dep
# so CI will always have it, but local envs might not.
pytest.importorskip("langchain_community.tools")


class TestOverrides:
    def test_requests_tools_carry_dangerous_flag(self) -> None:
        # RequestsGetTool / RequestsPostTool need
        # allow_dangerous_requests=True to actually work; the override
        # table ships that ctor.
        for cls in ("RequestsGetTool", "RequestsPostTool"):
            assert cls in _OVERRIDES
            assert "allow_dangerous_requests=True" in _OVERRIDES[cls]["ctor"]
            assert "extra_imports" in _OVERRIDES[cls]
            assert any(
                "TextRequestsWrapper" in imp
                for imp in _OVERRIDES[cls]["extra_imports"]
            )

    def test_tavily_has_descriptive_name_and_api_key_hint(self) -> None:
        entry = _OVERRIDES["TavilySearchResults"]
        assert entry.get("name") == "tavily_search"
        assert "TAVILY_API_KEY" in entry["description"]

    def test_pubmed_renamed(self) -> None:
        # Default class name is pub_med; the override exposes `pubmed`.
        assert _OVERRIDES["PubmedQueryRun"]["name"] == "pubmed"


class TestFindUtility:
    def test_matches_api_wrapper_pattern(self) -> None:
        utilities = {"WikipediaAPIWrapper": object}
        assert _find_utility("WikipediaQueryRun", utilities) == "WikipediaAPIWrapper"

    def test_returns_none_when_no_match(self) -> None:
        assert _find_utility("FooBar", {}) is None

    def test_tries_multiple_suffix_strips(self) -> None:
        # All these should be trimmed back to "Arxiv" and resolve.
        utilities = {"ArxivAPIWrapper": object}
        for cls_name in ("ArxivQueryRun", "ArxivSearchRun", "ArxivTool"):
            assert _find_utility(cls_name, utilities) == "ArxivAPIWrapper"


class TestDiscoverTools:
    def test_returns_nonempty_list(self) -> None:
        entries = discover_tools()
        assert len(entries) > 0

    def test_every_entry_has_static_imports_and_ctor(self) -> None:
        # Guarantees the compiled graph can statically import every
        # tool the builder might reference.
        for e in discover_tools():
            assert e["imports"], f"{e['name']} missing imports"
            assert e["ctor"], f"{e['name']} missing ctor"
            assert all(imp.startswith("from ") for imp in e["imports"])

    def test_source_tag_prefixes(self) -> None:
        sources = {e["source"].split(":", 1)[0] for e in discover_tools()}
        # Should only be community or experimental — builtin:/mcp: tags
        # were retired.
        assert sources <= {"community", "experimental"}

    def test_overrides_take_effect(self) -> None:
        # tavily_search should appear exactly once and honor the
        # override's custom name + ctor.
        entries = [e for e in discover_tools() if e["name"] == "tavily_search"]
        assert len(entries) == 1
        assert "max_results=5" in entries[0]["ctor"]

    def test_duckduckgo_search_discovered(self) -> None:
        # A zero-arg, no-API-key tool the builder falls back on by
        # default. Sanity check that generic discovery finds it.
        names = {e["name"] for e in discover_tools()}
        assert "duckduckgo_search" in names

    def test_ctor_trim_suffixes_order_matters(self) -> None:
        # `QueryRun` must come before `Run` so "ArxivQueryRun" trims to
        # "Arxiv" rather than "ArxivQuery".
        assert _CTOR_TRIM_SUFFIXES.index("QueryRun") < _CTOR_TRIM_SUFFIXES.index("Run")
