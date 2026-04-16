"""Slash command menu definitions per mode."""

MAIN_COMMANDS = [
    ("/chat", "Enter LLM chat mode"),
    ("/code", "Enter LLM code mode (with tools)"),
    ("/agents", "Enter agents mode"),
    ("/version", "Show the application version"),
    ("/help", "Show available commands"),
    ("/exit", "Quit"),
]

CHAT_COMMANDS_MENU = [
    ("/code", "Switch to code mode"),
    ("/models", "List/filter models"),
    ("/search", "Fuzzy search for models"),
    ("/fetchmodels", "Refresh model list from APIs"),
    ("/use", "Select a model"),
    ("/debug", "Inspect last LLM request/response"),
    ("/cls", "Clear screen"),
    ("/clc", "Clear conversation history"),
    ("/back", "Return to main mode"),
    ("/help", "Show available commands"),
    ("/exit", "Quit"),
]

CODE_COMMANDS_MENU = [
    ("/chat", "Switch to chat mode"),
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
    ("/back", "Return to main mode"),
    ("/help", "Show available commands"),
    ("/exit", "Quit"),
]

AGENTS_COMMANDS_MENU = [
    ("/server", "Show or set the langosh-server URL"),
    ("/list", "List graphs in langgraph.json"),
    ("/select", "Select a graph (creates a server thread)"),
    ("/create", "Create a new graph (LLM-generated, registered in langgraph.json)"),
    ("/edit", "Edit selected graph (LLM conversation; regen on save)"),
    ("/compile", "Regenerate __init__.py from definition.json"),
    ("/test", "Run on the server (--context key=val for overrides)"),
    ("/assistants", "List assistants for the selected graph"),
    ("/assistant", "Create, update, or delete an assistant"),
    ("/graph", "Visualize the selected graph"),
    ("/clc", "Reset the active thread"),
    ("/delete", "Delete a graph + langgraph.json entry"),
    ("/status", "Show git status (in agents repo)"),
    ("/commit", "Commit all changes (in agents repo)"),
    ("/back", "Return to main mode"),
    ("/help", "Show available commands"),
    ("/exit", "Quit"),
]

AGENT_EDIT_COMMANDS_MENU = [
    ("/plan", "Approve every tool call"),
    ("/auto", "Auto-approve reads, approve writes"),
    ("/test", "Run the graph in the active thread"),
    ("/debug", "Inspect last LLM request/response"),
    ("/cls", "Clear screen"),
    ("/clc", "Reset the active thread"),
    ("/done", "Exit edit mode"),
    ("/help", "Show available commands"),
    ("/exit", "Quit"),
]
