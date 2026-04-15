"""Agent test runner — compile and execute an agent with event capture."""

import asyncio
import json
import logging
import os
import time
from pathlib import Path

import langosh.state as state

from .compiler import compile_agent
from .store import AGENTS_DIR, load_agent

_AGENTS_DATA_DIR = os.path.join(os.path.expanduser("~"), ".langosh", "agents")

logger = logging.getLogger(__name__)


def _load_functions(agent_id: str) -> list[dict]:
    """Load all function files for an agent."""
    func_dir = os.path.join(AGENTS_DIR, agent_id, "functions")
    functions = []
    if os.path.isdir(func_dir):
        for f in sorted(Path(func_dir).glob("*.py")):
            functions.append({
                "name": f.stem,
                "code": f.read_text(),
            })
    return functions


async def _run_agent(graph, test_input: str, events: list[dict]) -> dict:
    """Run a compiled agent graph and capture events."""
    import uuid

    config = {"configurable": {"thread_id": f"test-{uuid.uuid4().hex[:8]}"}}
    input_data = {"messages": [{"role": "user", "content": test_input}]}

    result_text = ""
    final_state = {}

    async for mode, data in graph.astream(
        input_data,
        config,
        stream_mode=["updates", "values"],
    ):
        ts = time.monotonic()

        if mode == "updates":
            if isinstance(data, dict):
                for node_name, node_output in data.items():
                    events.append({
                        "type": "node_update",
                        "node": node_name,
                        "output_keys": list(node_output.keys()) if isinstance(node_output, dict) else [],
                        "preview": str(node_output)[:200] if node_output else "",
                        "timestamp": ts,
                    })
        elif mode == "values":
            if isinstance(data, dict):
                final_state = data

    # Extract result from final state
    if "messages" in final_state:
        msgs = final_state["messages"]
        if msgs and isinstance(msgs, list):
            last = msgs[-1]
            if isinstance(last, dict):
                result_text = last.get("content", "")
            elif hasattr(last, "content"):
                result_text = last.content
    elif "result" in final_state:
        result_text = str(final_state["result"])
    elif "summary" in final_state:
        result_text = str(final_state["summary"])
    else:
        # Use last non-empty string value
        for v in reversed(list(final_state.values())):
            if isinstance(v, str) and v.strip():
                result_text = v
                break

    return {"result": result_text, "final_state": {k: str(v)[:500] for k, v in final_state.items()}}


def _save_last_run(agent_id: str, run_data: dict) -> None:
    """Save the last test run results for debugging."""
    agent_dir = os.path.join(_AGENTS_DATA_DIR, agent_id)
    os.makedirs(agent_dir, exist_ok=True)
    path = os.path.join(agent_dir, "last_run.json")
    with open(path, "w") as f:
        json.dump(run_data, f, indent=2, ensure_ascii=False, default=str)


async def test_agent(agent_id: str, test_input: str) -> dict:
    """Test an agent locally. Returns {status, result, events, duration_ms, error}."""
    agent_data = load_agent(agent_id)
    if not agent_data:
        return {"status": "error", "error": f"Agent not found: {agent_id}", "events": [], "duration_ms": 0}

    definition = agent_data.get("definition")
    if not definition:
        return {"status": "error", "error": f"No definition.json for agent: {agent_id}", "events": [], "duration_ms": 0}

    functions = _load_functions(agent_id)

    # Compile
    try:
        graph = compile_agent(definition, functions)
    except Exception as e:
        return {"status": "error", "error": f"Compilation failed: {e}", "events": [], "duration_ms": 0}

    # Run with event capture
    events: list[dict] = []
    start = time.monotonic()

    try:
        result = await asyncio.wait_for(
            _run_agent(graph, test_input, events),
            timeout=300,
        )
        elapsed_ms = int((time.monotonic() - start) * 1000)
        run_data = {
            "status": "success",
            "result": result.get("result", ""),
            "final_state": result.get("final_state", {}),
            "events": events,
            "duration_ms": elapsed_ms,
            "test_input": test_input,
        }
    except asyncio.TimeoutError:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        run_data = {"status": "timeout", "error": "Agent timed out (5 min)", "events": events, "duration_ms": elapsed_ms, "test_input": test_input}
    except Exception as e:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        run_data = {"status": "error", "error": str(e), "events": events, "duration_ms": elapsed_ms, "test_input": test_input}

    _save_last_run(agent_id, run_data)
    return run_data
