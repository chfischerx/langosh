"""Persist conversation history and summaries to disk.

History lives **inside the agents repo** so it travels with the repo
rather than leaking across workspaces:

- `chat`             → `<repo>/.langosh/chat.json`
- `code`             → `<repo>/.langosh/code.json`
- `builder:<graph>`  → `<repo>/graphs/<graph>/.history.json`

Format (unchanged): `{"messages": [...], "summary": "..."}`.
"""

from __future__ import annotations

import json
from pathlib import Path

from .settings import get_agents_path


def _path_for(mode: str) -> Path:
    """Return the on-disk path for `mode`. See module docstring for layout."""
    root = get_agents_path()
    if mode == "chat":
        return root / ".langosh" / "chat.json"
    if mode == "code":
        return root / ".langosh" / "code.json"
    if mode.startswith("builder:"):
        graph_id = mode.split(":", 1)[1]
        return root / "graphs" / graph_id / ".history.json"
    raise ValueError(f"Unknown history mode: {mode!r}")


def load_history(mode: str) -> tuple[list[dict], str]:
    """Load conversation history and summary for a mode. Returns ([], '') if none."""
    path = _path_for(mode)
    if not path.is_file():
        return [], ""
    try:
        data = json.loads(path.read_text())
        if isinstance(data, dict):
            return data.get("messages", []), data.get("summary", "")
        if isinstance(data, list):
            # Legacy format: plain list of messages.
            return data, ""
    except (json.JSONDecodeError, OSError):
        pass
    return [], ""


def save_history(mode: str, messages: list[dict], summary: str = "") -> None:
    """Save conversation history and summary for a mode.

    Creates parent directories as needed — e.g. a fresh repo's
    `.langosh/` subfolder, or a graph's folder for a builder history.
    """
    path = _path_for(mode)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"messages": messages, "summary": summary}, ensure_ascii=False))


def clear_history(mode: str) -> None:
    """Delete conversation history for a mode (no-op if missing)."""
    path = _path_for(mode)
    if path.is_file():
        path.unlink()
