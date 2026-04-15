"""Persisted user settings stored in ~/.langosh/settings.json."""

import json
import os
from pathlib import Path

_SETTINGS_PATH = os.path.join(os.path.expanduser("~"), ".langosh", "settings.json")

DEFAULT_SERVER_URL = "http://localhost:8001"
_DEFAULT_AGENTS_DIR_NAME = "langosh-agents"


def _load() -> dict:
    if not os.path.isfile(_SETTINGS_PATH):
        return {}
    try:
        with open(_SETTINGS_PATH) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save(data: dict) -> None:
    os.makedirs(os.path.dirname(_SETTINGS_PATH), exist_ok=True)
    with open(_SETTINGS_PATH, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get(key: str, default=None):
    """Get a setting value."""
    return _load().get(key, default)


def set(key: str, value) -> None:
    """Set a setting value."""
    data = _load()
    data[key] = value
    _save(data)


def delete(key: str) -> None:
    """Remove a setting."""
    data = _load()
    data.pop(key, None)
    _save(data)


def get_agents_path() -> Path:
    """Resolve the path to the langosh-agents repo.

    Resolution order: env LANGOSH_AGENTS_PATH > settings.json `agents_path` >
    sibling directory `../langosh-agents/` next to the langosh repo.
    """
    env = os.environ.get("LANGOSH_AGENTS_PATH")
    if env:
        return Path(env).expanduser().resolve()
    stored = get("agents_path")
    if stored:
        return Path(stored).expanduser().resolve()
    # Fallback: sibling of the current working directory
    return (Path.cwd().parent / _DEFAULT_AGENTS_DIR_NAME).resolve()


def get_server_url() -> str:
    """Resolve the langosh-server URL.

    Resolution order: env LANGOSH_SERVER_URL > settings.json `server_url` >
    DEFAULT_SERVER_URL.
    """
    return (
        os.environ.get("LANGOSH_SERVER_URL")
        or get("server_url")
        or DEFAULT_SERVER_URL
    )
