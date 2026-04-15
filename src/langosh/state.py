"""Shared mutable state for the CLI application."""

from rich.console import Console

console = Console()

# Model catalog
model_cache: dict = {}
model_list: list = []
last_results: list = []

# Active model selection
active_model: dict = {"provider": None, "model_id": None}

# Mode state
current_mode: str = "main"
code_sub_mode: str = "auto"  # plan, auto, edit

# Per-mode conversation histories
chat_messages: list[dict] = []
code_messages: list[dict] = []

# Per-mode rolling summaries
chat_summary: str = ""
code_summary: str = ""

# Agent editing state
active_agent_id: str = ""
agent_sub_mode: str = "auto"  # plan, auto, edit
agent_messages: list[dict] = []
agent_summary: str = ""
agent_editing: bool = False

# Debug store for last LLM call
last_debug: dict = {}

# Sliding window size
WINDOW_SIZE = 20
