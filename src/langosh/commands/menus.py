"""Slash command menu definitions per mode."""

# Agents mode — no graph selected yet
AGENTS_COMMANDS_MENU = [
    ("/list", "List graphs in langgraph.json"),
    ("/select", "Select a graph and assistant"),
    ("/create", "Create a new graph (LLM-generated)"),
    ("/deploy", "Commit, push, and reload agents on the server"),
    ("/chat", "Switch to LLM chat mode"),
    ("/code", "Switch to LLM code mode (with tools)"),
    ("/admin", "Switch to server admin mode"),
    ("/models", "List/filter models"),
    ("/use", "Select a model"),
    ("/version", "Show the application version"),
    ("/help", "Show available commands"),
    ("/exit", "Quit"),
]

# Agents mode — graph selected
AGENTS_GRAPH_COMMANDS_MENU = [
    ("/run", "Run on the server (--context key=val for overrides)"),
    ("/edit", "Edit selected graph (LLM conversation; regen on save)"),
    ("/compile", "Regenerate __init__.py from definition.json"),
    ("/assistants", "List assistants for the selected graph"),
    ("/assistant", "Create, update, or delete an assistant"),
    ("/graph", "Visualize the selected graph"),
    ("/threads", "List threads — switch to a previous conversation"),
    ("/thread", "Show current thread info and conversation"),
    ("/thread new", "Start a new thread (keeps previous)"),
    ("/thread delete", "Delete a thread"),
    ("/clc", "Reset the active thread"),
    ("/delete", "Delete this graph + langgraph.json entry"),
    ("/select", "Switch to a different graph"),
    ("/create", "Create a new graph"),
    ("/deploy", "Commit, push, and reload agents on the server"),
    ("/status", "Show git status (in agents repo)"),
    ("/commit", "Commit all changes (in agents repo)"),
    ("/chat", "Switch to LLM chat mode"),
    ("/code", "Switch to LLM code mode (with tools)"),
    ("/admin", "Switch to server admin mode"),
    ("/help", "Show available commands"),
    ("/exit", "Quit"),
]

CHAT_COMMANDS_MENU = [
    ("/models", "List/filter models"),
    ("/search", "Fuzzy search for models"),
    ("/fetchmodels", "Refresh model list from APIs"),
    ("/use", "Select a model"),
    ("/debug", "Inspect last LLM request/response"),
    ("/cls", "Clear screen"),
    ("/clc", "Clear conversation history"),
    ("/code", "Switch to code mode"),
    ("/home", "Return to home"),
    ("/help", "Show available commands"),
    ("/exit", "Quit"),
]

CODE_COMMANDS_MENU = [
    ("/plan", "Approve every tool call"),
    ("/auto", "Auto-approve reads, approve writes"),
    ("/edit", "Auto-approve all tool calls"),
    ("/models", "List/filter models"),
    ("/search", "Fuzzy search for models"),
    ("/fetchmodels", "Refresh model list from APIs"),
    ("/use", "Select a model"),
    ("/debug", "Inspect last LLM request/response"),
    ("/cls", "Clear screen"),
    ("/clc", "Clear conversation history"),
    ("/chat", "Switch to chat mode"),
    ("/home", "Return to home"),
    ("/help", "Show available commands"),
    ("/exit", "Quit"),
]

AGENT_EDIT_COMMANDS_MENU = [
    ("/plan", "Approve every tool call"),
    ("/auto", "Auto-approve reads, approve writes"),
    ("/run", "Run the graph in the active thread"),
    ("/debug", "Inspect last LLM request/response"),
    ("/cls", "Clear screen"),
    ("/clc", "Reset the active thread"),
    ("/done", "Exit edit mode"),
    ("/help", "Show available commands"),
    ("/exit", "Quit"),
]

ADMIN_COMMANDS_MENU = [
    ("/server", "Show or set the langosh-server URL"),
    ("/info", "Show server info (version, graphs, status)"),
    ("/reload", "Hot-reload agents on the server"),
    ("/config", "View and edit server configuration"),
    ("/keys", "List API keys"),
    ("/key", "Manage API keys (create, delete, rotate)"),
    ("/home", "Return to home"),
    ("/help", "Show available commands"),
    ("/exit", "Quit"),
]
