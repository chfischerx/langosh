"""Shared mutable state for the CLI application."""

from rich.console import Console
from rich.theme import Theme

console = Console(theme=Theme({"dim": "grey70"}))

# Model catalog
model_cache: dict = {}
model_list: list = []
last_results: list = []

# Active model selection
active_model: dict = {"provider": None, "model_id": None}

# Sub-mode for code/agent editing (used by queries.py / agents/editor.py)
code_sub_mode: str = "auto"  # plan, auto, edit

# Per-mode conversation histories
chat_messages: list[dict] = []
code_messages: list[dict] = []

# Per-mode rolling summaries
chat_summary: str = ""
code_summary: str = ""

# Active server (display mirror of settings.active_server)
active_server_name: str = ""

# Agent editing state (used by agents/editor.py and agents/builder.py;
# mode instances set these when entering/exiting dev graph mode)
active_graph_id: str = ""
active_assistant_id: str = ""
active_thread_id: str = ""
agent_sub_mode: str = "auto"     # normal, plan, auto
agent_messages: list[dict] = []
agent_summary: str = ""
agent_editing: bool = False

# When a /create conversation is in progress, this holds the session state:
#   name, description, graph_id, graph_model, provider, model_id,
#   system_prompt, messages, total_in, total_out.
# While non-None, dev-mode free-text turns feed the builder instead of the
# editor. Cleared when the builder emits JSON or the user /cancels.
pending_create: dict | None = None

# Debug store for last LLM call
last_debug: dict = {}

# Sliding window size
WINDOW_SIZE = 20
