"""Persist conversation history and summaries to disk."""

import json
import os

_HISTORY_DIR = os.path.join(os.path.expanduser("~"), ".langosh", "history")


def load_history(mode: str) -> tuple[list[dict], str]:
    """Load conversation history and summary for a mode. Returns ([], '') if none."""
    path = os.path.join(_HISTORY_DIR, f"{mode}.json")
    if not os.path.isfile(path):
        return [], ""
    try:
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data.get("messages", []), data.get("summary", "")
        # Legacy format: plain list
        if isinstance(data, list):
            return data, ""
    except (json.JSONDecodeError, OSError):
        pass
    return [], ""


def save_history(mode: str, messages: list[dict], summary: str = "") -> None:
    """Save conversation history and summary for a mode."""
    os.makedirs(_HISTORY_DIR, exist_ok=True)
    path = os.path.join(_HISTORY_DIR, f"{mode}.json")
    with open(path, "w") as f:
        json.dump({"messages": messages, "summary": summary}, f, ensure_ascii=False)


def clear_history(mode: str) -> None:
    """Delete conversation history for a mode."""
    path = os.path.join(_HISTORY_DIR, f"{mode}.json")
    if os.path.isfile(path):
        os.remove(path)
