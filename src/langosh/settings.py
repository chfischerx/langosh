"""Persisted user settings stored in ~/.langosh/settings.json."""

import json
import os

_SETTINGS_PATH = os.path.join(os.path.expanduser("~"), ".langosh", "settings.json")


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
