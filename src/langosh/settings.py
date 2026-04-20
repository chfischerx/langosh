"""Persisted user settings stored in ~/.langosh/settings.json."""

import json
import os
from pathlib import Path

_SETTINGS_PATH = os.path.join(os.path.expanduser("~"), ".langosh", "settings.json")

DEFAULT_SERVER_URL = "http://localhost:2024"


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
    """Resolve the path to the agents repo.

    Resolution order: env LANGOSH_AGENTS_PATH > settings.json `agents_path`
    > current working directory.

    The default is cwd so running `langosh` inside a repo that was just
    scaffolded with /initrepo reads and writes against that repo.
    """
    env = os.environ.get("LANGOSH_AGENTS_PATH")
    if env:
        return Path(env).expanduser().resolve()
    stored = get("agents_path")
    if stored:
        return Path(stored).expanduser().resolve()
    return Path.cwd().resolve()


# ── Multi-server helpers ───────────────────────────────────────────────────


def get_servers() -> dict[str, dict]:
    """Return the full servers dict: {name: {url}}.

    Older settings files may also carry `api_key` or `langosh_server`
    fields — callers ignore them; they're kept on disk but no code path
    reads them. Server-level auth is out of scope for Langosh's local
    dev testing flows.
    """
    return _load().get("servers", {})


def get_active_server_name() -> str:
    """Return the name of the active server, or empty string if none."""
    return _load().get("active_server", "")


def set_active_server(name: str) -> None:
    """Switch the active server by name."""
    data = _load()
    if name not in data.get("servers", {}):
        raise ValueError(f"Unknown server: {name}")
    data["active_server"] = name
    _save(data)


def add_server(name: str, url: str) -> None:
    """Add a new named server."""
    data = _load()
    data.setdefault("servers", {})[name] = {"url": url}
    # If this is the first server, make it active automatically.
    if not data.get("active_server"):
        data["active_server"] = name
    _save(data)


def update_server(name: str, *, url: str | None = None) -> None:
    """Update fields on an existing server."""
    data = _load()
    server = data.get("servers", {}).get(name)
    if not server:
        raise ValueError(f"Unknown server: {name}")
    if url is not None:
        server["url"] = url
    _save(data)


def remove_server(name: str) -> None:
    """Remove a named server. Cannot remove the active server."""
    data = _load()
    if name not in data.get("servers", {}):
        raise ValueError(f"Unknown server: {name}")
    if data.get("active_server") == name:
        raise ValueError("Cannot remove the active server. Switch first.")
    del data["servers"][name]
    _save(data)


def get_server_url() -> str:
    """Resolve the server URL for the active server.

    Resolution order: env LANGOSH_SERVER_URL > active server in settings >
    DEFAULT_SERVER_URL.
    """
    env = os.environ.get("LANGOSH_SERVER_URL")
    if env:
        return env
    data = _load()
    active = data.get("active_server", "")
    server = data.get("servers", {}).get(active, {})
    return server.get("url") or DEFAULT_SERVER_URL


