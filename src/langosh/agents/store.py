"""Agent storage — create, save, list, load agents from ./agents/ directory."""

import json
import os
import re
from datetime import datetime, timezone

AGENTS_DIR = "./agents"


def name_to_id(name: str) -> str:
    """Convert a display name to a folder-safe agent ID."""
    agent_id = name.lower().strip()
    agent_id = re.sub(r"[^\w\s-]", "", agent_id)
    agent_id = re.sub(r"[\s-]+", "_", agent_id)
    return agent_id


def create_agent_folder(agent_id: str) -> str:
    """Create the agent folder structure. Returns the agent path."""
    agent_path = os.path.join(AGENTS_DIR, agent_id)
    os.makedirs(os.path.join(agent_path, "functions"), exist_ok=True)
    return agent_path


def save_metadata(agent_id: str, name: str, description: str) -> None:
    """Save agent metadata."""
    agent_path = os.path.join(AGENTS_DIR, agent_id)
    metadata = {
        "name": name,
        "description": description,
        "agent_id": agent_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(os.path.join(agent_path, "metadata.json"), "w") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)


def save_definition(agent_id: str, definition: dict) -> None:
    """Save agent definition JSON."""
    agent_path = os.path.join(AGENTS_DIR, agent_id)
    with open(os.path.join(agent_path, "definition.json"), "w") as f:
        json.dump(definition, f, indent=2, ensure_ascii=False)


def save_function(agent_id: str, name: str, code: str) -> None:
    """Save a function file for the agent."""
    func_path = os.path.join(AGENTS_DIR, agent_id, "functions", f"{name}.py")
    with open(func_path, "w") as f:
        f.write(code)


def list_agents() -> list[dict]:
    """List all agents by scanning ./agents/ and loading metadata."""
    if not os.path.isdir(AGENTS_DIR):
        return []
    agents = []
    for entry in sorted(os.listdir(AGENTS_DIR)):
        meta_path = os.path.join(AGENTS_DIR, entry, "metadata.json")
        if os.path.isfile(meta_path):
            try:
                with open(meta_path) as f:
                    metadata = json.load(f)
                agents.append(metadata)
            except (json.JSONDecodeError, OSError):
                agents.append({"agent_id": entry, "name": entry, "description": "(error reading metadata)"})
    return agents


def load_agent(agent_id: str) -> dict | None:
    """Load an agent's metadata and definition."""
    agent_path = os.path.join(AGENTS_DIR, agent_id)
    if not os.path.isdir(agent_path):
        return None

    result: dict = {"agent_id": agent_id}

    meta_path = os.path.join(agent_path, "metadata.json")
    if os.path.isfile(meta_path):
        with open(meta_path) as f:
            result["metadata"] = json.load(f)

    def_path = os.path.join(agent_path, "definition.json")
    if os.path.isfile(def_path):
        with open(def_path) as f:
            result["definition"] = json.load(f)

    func_dir = os.path.join(agent_path, "functions")
    if os.path.isdir(func_dir):
        result["functions"] = [f[:-3] for f in os.listdir(func_dir) if f.endswith(".py")]

    return result


def delete_agent(agent_id: str) -> bool:
    """Delete an agent folder and all its contents. Returns True if deleted."""
    import shutil

    agent_path = os.path.join(AGENTS_DIR, agent_id)
    if not os.path.isdir(agent_path):
        return False
    shutil.rmtree(agent_path)
    return True
