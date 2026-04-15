"""Agent compiler — compiles definition.json into a runnable LangGraph graph.

Adapted from deep_agents dynamic_loader.py for local CLI use.
"""

import asyncio
import json
import logging
import re
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

logger = logging.getLogger(__name__)

# Available agent tools — imported lazily to avoid circular imports
_TOOLS_CACHE: dict[str, Any] | None = None


def _get_available_tools() -> dict[str, Any]:
    """Lazily load all available agent tools."""
    global _TOOLS_CACHE
    if _TOOLS_CACHE is None:
        from .tools.files import edit_file, glob_files, grep_files, list_directory, read_file, write_file
        from .tools.python_exec import execute_python

        _TOOLS_CACHE = {
            "read_file": read_file,
            "write_file": write_file,
            "edit_file": edit_file,
            "list_directory": list_directory,
            "glob_files": glob_files,
            "grep_files": grep_files,
            "execute_python": execute_python,
        }

        # Optional tools — import only if dependencies available
        try:
            from .tools.websearch import web_search
            _TOOLS_CACHE["web_search"] = web_search
            _TOOLS_CACHE["internet_search"] = web_search  # alias
        except ImportError:
            pass
        try:
            from .tools.rss import fetch_rss
            _TOOLS_CACHE["fetch_rss"] = fetch_rss
        except ImportError:
            pass
        try:
            from .tools.slack import ask_slack, send_slack_message
            _TOOLS_CACHE["send_slack_message"] = send_slack_message
            _TOOLS_CACHE["ask_slack"] = ask_slack
        except ImportError:
            pass
        try:
            from .tools.telegram import ask_telegram, send_telegram_message
            _TOOLS_CACHE["send_telegram_message"] = send_telegram_message
            _TOOLS_CACHE["ask_telegram"] = ask_telegram
        except ImportError:
            pass

    return _TOOLS_CACHE


# Optional model override from definition.json ("provider:model_id" format)
_definition_model: str = ""


async def call_llm(prompt: str, system: str = "", max_tokens: int = 2048) -> str:
    """Call the LLM. Uses the definition's pinned model, or falls back to active model."""
    from ..config import DEFAULT_MODELS, get_settings
    from ..llm import call_llm_simple
    from ..state import active_model

    settings = get_settings()

    # Priority: definition model > active model > config default
    if _definition_model and ":" in _definition_model:
        provider, model_id = _definition_model.split(":", 1)
    else:
        provider = active_model["provider"] or settings.default_provider
        model_id = active_model["model_id"] or settings.default_model or DEFAULT_MODELS.get(provider, "")

    result = await call_llm_simple(
        provider, model_id, None,
        system=system or "You are a helpful assistant.",
        messages=[{"role": "user", "content": prompt}],
    )
    return result["text"]


def _resolve_tools(tool_names: list[str]) -> list:
    """Resolve tool name strings to callable tool functions."""
    available = _get_available_tools()
    resolved = []
    for name in tool_names:
        if name in available:
            resolved.append(available[name])
        else:
            logger.warning(f"Unknown tool '{name}', skipping")
    return resolved


def _build_state_class(schema: dict[str, str]) -> type:
    """Build a TypedDict class from a schema mapping field names to type names."""
    type_map = {"str": str, "int": int, "float": float, "bool": bool, "list": list, "dict": dict}
    annotations = {}
    for field, type_name in schema.items():
        annotations[field] = type_map.get(type_name, Any)
    return TypedDict("AgentState", annotations, total=False)  # type: ignore[misc]


def _load_node_function(code_str: str, node_name: str) -> Any:
    """Execute a code string and extract the named function."""
    available = _get_available_tools()
    namespace: dict[str, Any] = {
        "Any": Any,
        **available,
        "asyncio": asyncio,
        "json": json,
        "re": re,
        "logging": logging,
        "logger": logging.getLogger("agent"),
        "call_llm": call_llm,
    }
    exec(code_str, namespace)

    if node_name in namespace and callable(namespace[node_name]):
        return namespace[node_name]

    # Fallback: find first non-injected callable
    injected = {"Any", "asyncio", "json", "re", "logging", "logger", "call_llm", *available.keys()}
    for key, val in namespace.items():
        if callable(val) and not key.startswith("_") and key not in injected:
            return val

    raise ValueError(f"No callable function found for node '{node_name}'")


def _make_tool_node(node_def: dict) -> Any:
    """Generate a wrapper function for a tool-type node."""
    tool_name = node_def["tool"]
    static_args = node_def.get("args", {})
    args_from_state = node_def.get("args_from_state", {})
    output_field = node_def.get("output_field", "result")

    available = _get_available_tools()
    tool_func = available.get(tool_name)
    if not tool_func:
        raise ValueError(f"Unknown tool '{tool_name}'")

    import inspect

    async def _tool_wrapper(state):
        kwargs = dict(static_args)
        for arg_name, state_field in args_from_state.items():
            kwargs[arg_name] = state.get(state_field, "")

        if inspect.iscoroutinefunction(tool_func):
            result = await tool_func(**kwargs)
        else:
            result = tool_func(**kwargs)

        return {output_field: result}

    return _tool_wrapper


def _make_llm_node(node_def: dict) -> Any:
    """Generate a wrapper function for an llm-type node."""
    prompt_template = node_def.get("prompt_template", "{messages}")
    system = node_def.get("system", "")
    output_field = node_def.get("output_field", "result")
    max_tokens = node_def.get("max_tokens", 2048)

    async def _llm_wrapper(state):
        prompt = prompt_template
        for key, val in state.items():
            prompt = prompt.replace(f"{{{key}}}", str(val) if val else "")
        result = await call_llm(prompt=prompt, system=system, max_tokens=max_tokens)
        return {output_field: result}

    return _llm_wrapper


def _compile_simple(definition: dict, checkpointer) -> Any:
    """Compile a simple agent as a single-node graph using our LLM providers.

    Uses call_llm() which routes through our provider system (Anthropic API,
    Bedrock, OpenAI, Claude SDK) — handles auth automatically.
    """
    system_prompt = definition.get("system_prompt", "You are a helpful assistant.")
    tool_names = definition.get("tools", [])
    tools = _resolve_tools(tool_names)

    # Build a simple graph: __start__ → agent → __end__
    StateClass = _build_state_class({"messages": "list", "result": "str"})
    builder = StateGraph(StateClass)

    async def agent_node(state):
        messages = state.get("messages", [])
        # Extract the last user message
        user_msg = ""
        for m in reversed(messages):
            if isinstance(m, dict) and m.get("role") == "user":
                user_msg = m.get("content", "")
                break
            elif hasattr(m, "content") and hasattr(m, "type") and m.type == "human":
                user_msg = m.content
                break

        if not user_msg:
            return {"result": "(no user message found)"}

        # Build tool descriptions for the system prompt
        tool_desc = ""
        if tools:
            import inspect
            descs = []
            for t in tools:
                name = getattr(t, "__name__", str(t))
                doc = (getattr(t, "__doc__", "") or "").strip().split("\n")[0]
                descs.append(f"- {name}: {doc}")
            tool_desc = "\n\nAvailable tools:\n" + "\n".join(descs)

        full_system = system_prompt + tool_desc
        result = await call_llm(prompt=user_msg, system=full_system)
        return {"result": result}

    builder.add_node("agent", agent_node)
    builder.add_edge(START, "agent")
    builder.add_edge("agent", END)

    return builder.compile(checkpointer=checkpointer)


def _compile_custom(definition: dict, functions: list[dict], checkpointer) -> Any:
    """Compile a custom StateGraph agent."""
    state_schema = definition.get("state_schema", {"messages": "list"})
    StateClass = _build_state_class(state_schema)

    builder = StateGraph(StateClass)

    # Load function code
    func_map: dict[str, Any] = {}
    for func_def in functions:
        name = func_def["name"]
        code = func_def["code"]
        func_map[name] = _load_node_function(code, name)

    # Add nodes
    for node_def in definition.get("nodes", []):
        name = node_def["name"]
        node_type = node_def.get("type", "function")

        if node_type == "tool":
            builder.add_node(name, _make_tool_node(node_def))
        elif node_type == "llm":
            builder.add_node(name, _make_llm_node(node_def))
        elif node_type == "function":
            if name in func_map:
                builder.add_node(name, func_map[name])
            else:
                logger.warning(f"No function found for node '{name}'")
        else:
            logger.warning(f"Unknown node type '{node_type}' for '{name}'")

    # Add edges
    for edge_def in definition.get("edges", []):
        src = edge_def["from"]
        dst = edge_def.get("to")

        src_node = START if src == "__start__" else src
        dst_node = END if dst == "__end__" else dst

        if edge_def.get("conditional"):
            mapping = edge_def.get("mapping", {})
            resolved = {k: (END if v == "__end__" else v) for k, v in mapping.items()}
            router_func = func_map.get(src)
            if router_func:
                builder.add_conditional_edges(src_node, router_func, resolved)
        else:
            builder.add_edge(src_node, dst_node)

    return builder.compile(checkpointer=checkpointer)


def compile_agent(definition: dict, functions: list[dict]) -> Any:
    """Compile an agent definition + functions into a runnable graph.

    Uses InMemorySaver for checkpointing (no database needed).
    If the definition includes a "model" field (e.g. "claude_sdk:claude-sonnet-4-6"),
    it overrides the active model for all LLM calls within this agent.
    """
    global _definition_model
    _definition_model = definition.get("model", "")

    checkpointer = InMemorySaver()
    agent_type = definition.get("type", "simple")

    if agent_type == "simple":
        return _compile_simple(definition, checkpointer)
    else:
        return _compile_custom(definition, functions, checkpointer)
