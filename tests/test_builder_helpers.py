"""Pure-logic tests for the graph builder helpers."""

from __future__ import annotations

from langosh.graphs.builder import (
    _extract_functions,
    _extract_json_block,
    _name_to_id,
)


class TestNameToId:
    def test_lowercases_and_underscores(self) -> None:
        assert _name_to_id("My Graph") == "my_graph"

    def test_strips_punctuation(self) -> None:
        assert _name_to_id("News!Summarizer?") == "newssummarizer"

    def test_collapses_runs_of_whitespace_and_dashes(self) -> None:
        assert _name_to_id("my   cool --  agent") == "my_cool_agent"

    def test_strips_leading_trailing_whitespace(self) -> None:
        assert _name_to_id("   hello world  ") == "hello_world"

    def test_keeps_existing_underscores(self) -> None:
        assert _name_to_id("my_agent") == "my_agent"


class TestExtractJsonBlock:
    def test_extracts_first_block(self) -> None:
        text = 'blah blah\n```json\n{"type": "simple"}\n```\nmore blah'
        assert _extract_json_block(text) == {"type": "simple"}

    def test_returns_none_when_no_block(self) -> None:
        assert _extract_json_block("no code here") is None

    def test_returns_none_on_invalid_json(self) -> None:
        text = "```json\n{not valid}\n```"
        assert _extract_json_block(text) is None

    def test_handles_multiline_body(self) -> None:
        text = (
            "Here is the agent:\n\n"
            "```json\n"
            '{\n'
            '  "type": "custom",\n'
            '  "nodes": [{"name": "a", "type": "tool"}]\n'
            '}\n'
            "```\n"
        )
        parsed = _extract_json_block(text)
        assert parsed is not None
        assert parsed["type"] == "custom"
        assert parsed["nodes"][0]["name"] == "a"


class TestExtractFunctions:
    def test_extracts_function_nodes_and_rewrites_in_place(self) -> None:
        definition = {
            "type": "custom",
            "nodes": [
                {"name": "tool_a", "type": "tool", "tool": "web_search"},
                {
                    "name": "transform",
                    "type": "function",
                    "code": "async def transform(state):\n    return state\n",
                },
            ],
        }
        functions = _extract_functions(definition)
        assert functions == [
            {
                "name": "transform",
                "code": "async def transform(state):\n    return state\n",
            }
        ]
        # Function-node's inline code is replaced with a file reference.
        transform_node = definition["nodes"][1]
        assert "code" not in transform_node
        assert transform_node["code_file"] == "functions/transform.py"
        # Tool nodes are untouched.
        assert definition["nodes"][0]["tool"] == "web_search"

    def test_returns_empty_list_when_no_function_nodes(self) -> None:
        definition = {
            "type": "custom",
            "nodes": [{"name": "a", "type": "tool", "tool": "x"}],
        }
        assert _extract_functions(definition) == []

    def test_handles_missing_nodes_key(self) -> None:
        # Simple agents don't have `nodes`.
        definition = {"type": "simple", "system_prompt": "x"}
        assert _extract_functions(definition) == []
