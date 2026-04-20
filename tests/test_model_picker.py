"""Tests for the shared interactive model picker constants + styling."""

from __future__ import annotations

from langosh.model_picker import LANGCHAIN_EXCLUDE, _autocomplete_style


class TestLangChainExclude:
    def test_excludes_claude_sdk(self) -> None:
        # claude_sdk is CLI-only — must never reach a deployed graph.
        assert "claude_sdk" in LANGCHAIN_EXCLUDE

    def test_is_frozen(self) -> None:
        # Should not be mutable at runtime.
        assert isinstance(LANGCHAIN_EXCLUDE, frozenset)

    def test_does_not_exclude_real_providers(self) -> None:
        for real in ("anthropic", "openai", "bedrock_converse"):
            assert real not in LANGCHAIN_EXCLUDE


class TestAutocompleteStyle:
    def test_style_built_without_error(self) -> None:
        style = _autocomplete_style()
        # questionary's Style exposes style_rules as a list of tuples.
        assert len(style.style_rules) >= 3

    def test_current_completion_uses_orange_accent(self) -> None:
        # The selected-completion rule should apply the #f44336 orange
        # that matches questionary's default `answer` color — the user
        # explicitly asked for this to match the text-input accent.
        rules = dict(_autocomplete_style().style_rules)
        current = rules.get("completion-menu.completion.current", "")
        assert "#f44336" in current

    def test_scrollbar_styled(self) -> None:
        # Ensure we cover scrollbar classes so the menu doesn't render
        # as a bare terminal-default scrollbar on top of the dark bg.
        rules = dict(_autocomplete_style().style_rules)
        assert "scrollbar.background" in rules
        assert "scrollbar.button" in rules
