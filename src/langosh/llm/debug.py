"""Debug capture for raw LLM request/response JSON."""

import json

from rich.syntax import Syntax

# Stores the last raw request and response per API call.
# Each provider updates this after every call.
last_request: dict = {}
last_response: dict = {}


def capture_request(data: dict) -> None:
    """Store the raw request body."""
    last_request.clear()
    last_request.update(data)


def capture_response(data: dict) -> None:
    """Store the raw response body."""
    last_response.clear()
    last_response.update(data)


def format_json(data: dict, max_length: int = 0) -> str:
    """Pretty-print a dict as JSON string. Optionally truncate."""
    text = json.dumps(data, indent=2, ensure_ascii=False, default=str)
    if max_length and len(text) > max_length:
        return text[:max_length] + f"\n... (truncated, {len(text)} chars total)"
    return text


def syntax_json(data: dict, max_length: int = 0) -> Syntax:
    """Return a Rich Syntax object for syntax-highlighted JSON display."""
    text = format_json(data, max_length)
    return Syntax(text, "json", theme="github-dark", word_wrap=True)
