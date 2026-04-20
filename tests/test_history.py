"""Tests for per-repo conversation-history storage."""

from __future__ import annotations

import json

import pytest

from langosh.history import _path_for, clear_history, load_history, save_history


class TestPathFor:
    def test_chat_path(self, agents_path) -> None:
        assert _path_for("chat") == agents_path / ".langosh" / "chat.json"

    def test_code_path(self, agents_path) -> None:
        assert _path_for("code") == agents_path / ".langosh" / "code.json"

    def test_builder_path(self, agents_path) -> None:
        assert _path_for("builder:my_graph") == (
            agents_path / "graphs" / "my_graph" / ".history.json"
        )

    def test_unknown_mode_raises(self, agents_path) -> None:
        with pytest.raises(ValueError, match="Unknown history mode"):
            _path_for("weird")


class TestRoundTrip:
    def test_empty_load_when_no_file(self, agents_path) -> None:
        msgs, summary = load_history("chat")
        assert msgs == []
        assert summary == ""

    def test_save_then_load(self, agents_path) -> None:
        messages = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        save_history("chat", messages, "short summary")
        loaded_msgs, loaded_summary = load_history("chat")
        assert loaded_msgs == messages
        assert loaded_summary == "short summary"

    def test_save_creates_parent_dirs(self, agents_path) -> None:
        save_history("builder:nested_graph", [{"role": "user", "content": "x"}])
        path = agents_path / "graphs" / "nested_graph" / ".history.json"
        assert path.exists()
        payload = json.loads(path.read_text())
        assert payload["messages"][0]["content"] == "x"

    def test_clear_removes_file(self, agents_path) -> None:
        save_history("code", [{"role": "user", "content": "x"}])
        assert (agents_path / ".langosh" / "code.json").exists()
        clear_history("code")
        assert not (agents_path / ".langosh" / "code.json").exists()

    def test_clear_noop_when_missing(self, agents_path) -> None:
        # Must not raise.
        clear_history("chat")

    def test_legacy_plain_list_still_loads(self, agents_path) -> None:
        # Old format was a bare list of messages, not {messages, summary}.
        path = agents_path / ".langosh" / "chat.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([{"role": "user", "content": "legacy"}]))
        msgs, summary = load_history("chat")
        assert msgs[0]["content"] == "legacy"
        assert summary == ""

    def test_corrupt_file_returns_empty(self, agents_path) -> None:
        path = agents_path / ".langosh" / "chat.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{{not json")
        msgs, summary = load_history("chat")
        assert msgs == []
        assert summary == ""
