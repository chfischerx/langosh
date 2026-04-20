"""Tests for JSON → Python code generation.

The compiler is the load-bearing piece between what the LLM writes
(`definition.json`) and what the server runs. Broken output is worse
than a lint failure — it ships silently until runtime.
"""

from __future__ import annotations

import ast

import pytest

pytest.importorskip("langchain_community.tools")  # needed to compile any tool


from langosh.graphs.codegen import compile_to_source  # noqa: E402

SIMPLE_NO_TOOLS = {
    "type": "simple",
    "system_prompt": "You are a friendly assistant.",
    "tools": [],
    "context": {
        "model_name": {"type": "str", "default": "anthropic:claude-sonnet-4-5-20250929"},
        "model_provider": {"type": "str", "default": ""},
        "system_prompt": {"type": "str", "default": "You are a friendly assistant."},
    },
}


SIMPLE_WITH_TOOL = {
    "type": "simple",
    "system_prompt": "Search the web for the user.",
    "tools": ["duckduckgo_search"],
    "context": {
        "model_name": {"type": "str", "default": "anthropic:claude-sonnet-4-5-20250929"},
        "model_provider": {"type": "str", "default": ""},
        "system_prompt": {"type": "str", "default": "Search."},
    },
}


CUSTOM_SIMPLE_PIPELINE = {
    "type": "custom",
    "state": {
        "user_query": "str",
        "polished_answer": "str",
    },
    "context": {
        "model_name": {"type": "str", "default": "anthropic:claude-sonnet-4-5-20250929"},
        "model_provider": {"type": "str", "default": ""},
        "system_prompt": {"type": "str", "default": "You polish text."},
    },
    "nodes": [
        {
            "name": "polish",
            "type": "llm",
            "system": "You are a concise summarizer.",
            "prompt_template": "Polish this: {user_query}",
            "output_field": "polished_answer",
        },
    ],
    "edges": [
        {"from": "__start__", "to": "polish"},
        {"from": "polish", "to": "__end__"},
    ],
}


def _assert_valid_python(source: str) -> None:
    """The emitted source must parse. If not, something's broken upstream."""
    try:
        ast.parse(source)
    except SyntaxError as exc:
        msg = f"Generated Python is not syntactically valid: {exc}\n\n{source}"
        raise AssertionError(msg) from exc


class TestSimpleAgent:
    def test_parses_without_tools(self) -> None:
        src = compile_to_source(SIMPLE_NO_TOOLS, [], "demo")
        _assert_valid_python(src)

    def test_emits_state_graph_builder(self) -> None:
        src = compile_to_source(SIMPLE_NO_TOOLS, [], "demo")
        assert "_builder = StateGraph(State, context_schema=ContextSchema)" in src
        assert "graph = _builder" in src

    def test_has_init_model_helper(self) -> None:
        src = compile_to_source(SIMPLE_NO_TOOLS, [], "demo")
        # The helper is how we thread model_provider through reliably.
        assert "def _init_model(name, provider):" in src
        assert "init_chat_model(name, model_provider=provider)" in src

    def test_default_model_provider_env_var_emitted(self) -> None:
        src = compile_to_source(SIMPLE_NO_TOOLS, [], "demo")
        assert 'DEFAULT_MODEL_PROVIDER = os.environ.get("DEFAULT_MODEL_PROVIDER", "")' in src

    def test_tool_reference_becomes_static_import(self, tool_catalog) -> None:
        src = compile_to_source(SIMPLE_WITH_TOOL, [], "demo")
        # No runtime tool discovery — DuckDuckGo must be imported directly.
        assert "DuckDuckGoSearchRun" in src
        assert "_tools_by_name" in src

    def test_context_schema_contains_every_declared_field(self) -> None:
        src = compile_to_source(SIMPLE_NO_TOOLS, [], "demo")
        for field in ("model_name", "model_provider", "system_prompt"):
            assert f"{field}:" in src

    def test_pinned_model_replaces_env_fallback(self) -> None:
        # The pinned-model path only fires for context-less simple agents;
        # context-aware ones thread the model through runtime.context and
        # always keep the DEFAULT_MODEL env-var fallback.
        no_ctx = {
            "type": "simple",
            "system_prompt": "hi",
            "tools": [],
            "model": "openai:gpt-4o",
        }
        src = compile_to_source(no_ctx, [], "demo")
        assert "DEFAULT_MODEL = 'openai:gpt-4o'" in src
        # Env-var fallback should be absent in this path.
        assert 'os.environ.get("DEFAULT_MODEL"' not in src


class TestCustomAgent:
    def test_parses(self) -> None:
        src = compile_to_source(CUSTOM_SIMPLE_PIPELINE, [], "pipeline")
        _assert_valid_python(src)

    def test_emits_typed_dict_for_state(self) -> None:
        src = compile_to_source(CUSTOM_SIMPLE_PIPELINE, [], "pipeline")
        assert "class State(TypedDict):" in src
        assert "user_query: str" in src

    def test_node_function_emitted(self) -> None:
        src = compile_to_source(CUSTOM_SIMPLE_PIPELINE, [], "pipeline")
        assert "async def _polish(" in src
        # Output field gets written back into state.
        assert "'polished_answer': last_msg.content" in src or \
               '"polished_answer": last_msg.content' in src or \
               "'polished_answer':" in src


class TestErrorPaths:
    def test_unknown_type_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown agent type"):
            compile_to_source({"type": "weird"}, [], "x")

    def test_custom_without_state_raises(self) -> None:
        defn = {"type": "custom", "nodes": [], "edges": []}
        with pytest.raises(ValueError, match="state"):
            compile_to_source(defn, [], "x")

    def test_unknown_tool_raises_clear_error(self) -> None:
        defn = {
            "type": "simple",
            "system_prompt": "x",
            "tools": ["this_tool_does_not_exist_xyz"],
        }
        with pytest.raises(ValueError, match="this_tool_does_not_exist_xyz"):
            compile_to_source(defn, [], "x")
