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
    ("/select", "Select an agent"),
    ("/create", "Create a new agent"),
    ("/edit", "Edit selected agent (LLM conversation)"),
    ("/test", "Test selected agent locally"),
    ("/list", "List existing agents"),
    ("/delete", "Delete an agent"),
    ("/status", "Show git status"),
    ("/commit", "Commit all changes"),
    ("/back", "Return to main mode"),
    ("/help", "Show available commands"),
    ("/exit", "Quit"),
]

AGENT_EDIT_COMMANDS_MENU = [
    ("/plan", "Approve every tool call"),
    ("/auto", "Auto-approve reads, approve writes"),
    ("/test", "Test the agent"),
    ("/debug", "Inspect last LLM request/response"),
    ("/cls", "Clear screen"),
    ("/clc", "Clear agent conversation"),
    ("/done", "Exit edit mode"),
    ("/help", "Show available commands"),
    ("/exit", "Quit"),
]
