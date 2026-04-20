"""Tests for the `/initrepo` scaffold flow."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("langchain_community.tools")

from langosh.init_repo import _build_example_definition, init_repo  # noqa: E402


class TestBuildExampleDefinition:
    def test_splits_provider_prefix(self) -> None:
        defn = _build_example_definition("anthropic:claude-sonnet-4-5-20250929")
        ctx = defn["context"]
        assert ctx["model_name"]["default"] == "claude-sonnet-4-5-20250929"
        assert ctx["model_provider"]["default"] == "anthropic"

    def test_bedrock_with_colons_in_id(self) -> None:
        # The whole value after the first colon stays in model_name —
        # even if it itself contains colons (Bedrock inference profiles).
        defn = _build_example_definition(
            "bedrock_converse:global.anthropic.claude-sonnet-4-5-20250929-v1:0"
        )
        ctx = defn["context"]
        assert ctx["model_provider"]["default"] == "bedrock_converse"
        assert (
            ctx["model_name"]["default"]
            == "global.anthropic.claude-sonnet-4-5-20250929-v1:0"
        )

    def test_without_prefix_leaves_provider_empty(self) -> None:
        defn = _build_example_definition("claude-sonnet-4-5-20250929")
        ctx = defn["context"]
        assert ctx["model_provider"]["default"] == ""
        assert ctx["model_name"]["default"] == "claude-sonnet-4-5-20250929"

    def test_produces_simple_type(self) -> None:
        defn = _build_example_definition("anthropic:claude-sonnet-4-5-20250929")
        assert defn["type"] == "simple"
        assert defn["tools"] == []


class TestInitRepo:
    def test_scaffolds_expected_top_level_files(self, agents_path) -> None:
        init_repo(agents_path, name="demo", description="demo")
        expected = {
            ".env",
            ".env.example",
            ".gitignore",
            "README.md",
            "langgraph.json",
            "pyproject.toml",
            "graphs",
        }
        assert set(p.name for p in agents_path.iterdir()) >= expected

    def test_langgraph_json_registers_example_graph(self, agents_path) -> None:
        init_repo(agents_path, name="demo", description="demo")
        lg = json.loads((agents_path / "langgraph.json").read_text())
        assert "example" in lg["graphs"]
        # Standard LangSmith-deploy fields should all be present.
        assert lg.get("env") == ".env"
        assert lg.get("image_distro") == "wolfi"

    def test_env_file_pre_filled(self, agents_path) -> None:
        init_repo(agents_path, name="demo-repo", description="demo")
        env = (agents_path / ".env").read_text()
        assert "LANGSMITH_PROJECT=demo-repo" in env
        assert "LANGSMITH_API_KEY=" in env
        assert "DEFAULT_MODEL=" in env

    def test_gitignore_covers_env_and_history(self, agents_path) -> None:
        init_repo(agents_path, name="demo", description="demo")
        gi = (agents_path / ".gitignore").read_text()
        assert ".env" in gi
        assert ".langosh/" in gi
        assert "**/.history.json" in gi

    def test_example_graph_compiled_and_loadable(self, agents_path) -> None:
        init_repo(agents_path, name="demo", description="demo")
        init_py = agents_path / "graphs" / "example" / "__init__.py"
        assert init_py.exists()
        # compile_hash sanity tag gets written alongside.
        assert (agents_path / "graphs" / "example" / ".compile_hash").exists()
        # Source must be valid Python.
        import ast
        ast.parse(init_py.read_text())

    def test_custom_default_model_threaded_into_example(self, agents_path) -> None:
        init_repo(
            agents_path,
            name="demo",
            description="demo",
            default_model="openai:gpt-4o",
        )
        defn = json.loads((agents_path / "graphs" / "example" / "definition.json").read_text())
        assert defn["context"]["model_provider"]["default"] == "openai"
        assert defn["context"]["model_name"]["default"] == "gpt-4o"

    def test_refuses_on_non_empty_dir(self, agents_path) -> None:
        (agents_path / "some_file.txt").write_text("pre-existing")
        with pytest.raises(RuntimeError, match="directory is not empty"):
            init_repo(agents_path, name="demo", description="demo")

    def test_toml_escapes_quotes_and_backslashes(self, agents_path) -> None:
        init_repo(
            agents_path,
            name='tricky"name',
            description='has "quotes" and \\ backslash',
        )
        py = (agents_path / "pyproject.toml").read_text()
        # Survived as escaped TOML strings; no broken pyproject.
        assert r'\"' in py or r'"' not in py.split("name =", 1)[1].split("\n", 1)[0][2:-1]
        # The TOML must still parse.
        import tomllib
        parsed = tomllib.loads(py)
        assert parsed["project"]["name"] == 'tricky"name'
