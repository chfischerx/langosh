"""Python execution tool for LangGraph agents — typed wrapper around LLM tool."""

from ...llm.tools.python_exec import execute_python as _execute_python


async def execute_python(code: str) -> str:
    """Execute Python code in a sandboxed subprocess.

    Set a top-level `result` variable to return a value.
    Stdout is captured and returned.

    Args:
        code: Python source code to execute
    """
    return await _execute_python({"code": code})
