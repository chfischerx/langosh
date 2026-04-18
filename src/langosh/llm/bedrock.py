"""AWS Bedrock Converse multi-turn tool-calling loop with streaming + prompt caching."""

import asyncio
import json as _json
import logging

from ..config import get_settings
from .debug import capture_request, capture_response
from .types import LLMResult, ToolDispatcher, ToolEventCallback

logger = logging.getLogger(__name__)

try:
    import boto3
except ImportError:
    boto3 = None  # type: ignore[assignment]


def _require_sdk() -> None:
    if boto3 is None:
        raise ImportError(
            "The 'boto3' package is required for the AWS Bedrock provider. "
            "Install it with: pip install langosh[bedrock]"
        )


def tools_to_bedrock_format(tools: list[dict]) -> list[dict]:
    """Convert Anthropic-style tool schemas to Bedrock toolSpec format."""
    return [
        {
            "toolSpec": {
                "name": t["name"],
                "description": t["description"],
                "inputSchema": {"json": t["input_schema"]},
            },
        }
        for t in tools
    ]


def _to_bedrock_msgs(msgs: list[dict]) -> list[dict]:
    """Convert standard messages to Bedrock Converse format."""
    out = []
    for m in msgs:
        role = m.get("role", "user")
        content = m.get("content", "")
        if isinstance(content, str):
            text = content.strip() if content.strip() else "(empty)"
            out.append({"role": role, "content": [{"text": text}]})
        elif isinstance(content, list):
            filtered = []
            for block in content:
                if isinstance(block, dict) and "text" in block:
                    t = block["text"].strip() if block["text"].strip() else "(empty)"
                    filtered.append({"text": t})
                else:
                    filtered.append(block)
            out.append({"role": role, "content": filtered or [{"text": "(empty)"}]})
        else:
            text = str(content).strip() or "(empty)"
            out.append({"role": role, "content": [{"text": text}]})
    return out


def _drain_stream_sync(stream, on_chunk) -> dict:
    """Iterate Bedrock event stream synchronously; call on_chunk(text) for text deltas.

    Returns a dict with: content_blocks, stop_reason, usage.
    """
    content_blocks: list[dict] = []
    # Track per-index content block being built.
    current: dict[int, dict] = {}
    stop_reason = ""
    usage: dict = {}

    for event in stream:
        if "contentBlockStart" in event:
            start = event["contentBlockStart"]
            idx = start.get("contentBlockIndex", 0)
            block_start = start.get("start", {})
            if "toolUse" in block_start:
                tu = block_start["toolUse"]
                current[idx] = {
                    "toolUse": {
                        "toolUseId": tu["toolUseId"],
                        "name": tu["name"],
                        "_input_json": "",
                    }
                }
            else:
                current[idx] = {"text": ""}
        elif "contentBlockDelta" in event:
            cbd = event["contentBlockDelta"]
            idx = cbd.get("contentBlockIndex", 0)
            delta = cbd.get("delta", {})
            slot = current.setdefault(idx, {"text": ""})
            if "text" in delta:
                text = delta["text"]
                slot.setdefault("text", "")
                slot["text"] += text
                on_chunk(text)
            elif "toolUse" in delta:
                tu_delta = delta["toolUse"]
                # If slot has no toolUse yet (no contentBlockStart seen), initialize
                if "toolUse" not in slot:
                    slot = {"toolUse": {"toolUseId": "", "name": "", "_input_json": ""}}
                    current[idx] = slot
                if "input" in tu_delta:
                    slot["toolUse"]["_input_json"] += tu_delta["input"]
        elif "contentBlockStop" in event:
            idx = event["contentBlockStop"].get("contentBlockIndex", 0)
            slot = current.get(idx)
            if slot is None:
                continue
            if "toolUse" in slot:
                tu = slot["toolUse"]
                input_json = tu.pop("_input_json", "")
                try:
                    tu["input"] = _json.loads(input_json) if input_json else {}
                except _json.JSONDecodeError:
                    tu["input"] = {}
            content_blocks.append(slot)
        elif "messageStop" in event:
            stop_reason = event["messageStop"].get("stopReason", "")
        elif "metadata" in event:
            usage = event["metadata"].get("usage", {}) or {}

    return {"content": content_blocks, "stop_reason": stop_reason, "usage": usage}


async def _stream_turn(bedrock, request_body: dict, on_event):
    """Stream a Bedrock converse turn; emit token events; return (content, stop_reason, usage)."""
    resp = await asyncio.to_thread(bedrock.converse_stream, **request_body)
    stream = resp["stream"]
    loop = asyncio.get_event_loop()

    def _on_chunk(text: str) -> None:
        if on_event is not None:
            asyncio.run_coroutine_threadsafe(on_event("token", {"text": text}), loop)

    result = await asyncio.to_thread(_drain_stream_sync, stream, _on_chunk)
    return result


async def call_bedrock_with_tools(
    model_id: str,
    api_key: str | None,
    system: str,
    messages: list[dict],
    tools: list[dict],
    tool_dispatcher: ToolDispatcher,
    on_event: ToolEventCallback | None = None,
    max_tool_turns: int | None = None,
) -> LLMResult:
    """Multi-turn Bedrock Converse call with streaming tool-use and prompt caching."""
    _require_sdk()
    import os

    settings = get_settings()
    max_tool_turns = max_tool_turns if max_tool_turns is not None else settings.max_tool_turns

    if api_key and not settings.aws_bedrock_use_iam_role:
        os.environ["AWS_BEARER_TOKEN_BEDROCK"] = api_key
    bedrock = boto3.client("bedrock-runtime", region_name=settings.aws_bedrock_region)

    total_input = 0
    total_output = 0
    total_cache_read = 0
    total_cache_write = 0
    tool_calls_log: list[dict] = []
    tool_config = {
        "tools": [*tools_to_bedrock_format(tools), {"cachePoint": {"type": "default"}}]
    }

    conv = _to_bedrock_msgs(messages)
    cached_system = [{"text": system}, {"cachePoint": {"type": "default"}}]

    for turn in range(max_tool_turns + 1):
        request_body = {
            "modelId": model_id,
            "system": cached_system,
            "messages": conv,
            "toolConfig": tool_config,
            "inferenceConfig": {"maxTokens": settings.max_tokens},
        }
        capture_request(request_body)
        result = await _stream_turn(bedrock, request_body, on_event)
        capture_response(result)
        usage = result["usage"] or {}
        total_input += usage.get("inputTokens", 0)
        total_output += usage.get("outputTokens", 0)
        total_cache_read += usage.get("cacheReadInputTokens", 0)
        total_cache_write += usage.get("cacheWriteInputTokens", 0)

        stop_reason = result["stop_reason"]
        content_blocks = result["content"]

        def _result(text: str) -> LLMResult:
            return LLMResult(
                text=text,
                input_tokens=total_input,
                output_tokens=total_output,
                cache_read_input_tokens=total_cache_read,
                cache_creation_input_tokens=total_cache_write,
                tool_calls=tool_calls_log,
            )

        if stop_reason != "tool_use":
            text_parts = [b["text"] for b in content_blocks if "text" in b]
            return _result("\n".join(text_parts).strip())

        if turn >= max_tool_turns:
            text_parts = [b["text"] for b in content_blocks if "text" in b]
            text = ("\n".join(text_parts) or "[Reached tool-use turn cap]").strip()
            text += "\n\n_Note: Stopped after reaching the tool-use turn limit._"
            return _result(text)

        conv.append({"role": "assistant", "content": content_blocks})
        tool_result_blocks: list[dict] = []
        for block in content_blocks:
            if "toolUse" not in block:
                continue
            tu = block["toolUse"]
            if on_event:
                await on_event("tool_call", {"name": tu["name"], "input": tu.get("input") or {}})
            result_str = await tool_dispatcher(tu["name"], tu.get("input") or {})
            tool_calls_log.append({
                "name": tu["name"],
                "input": tu.get("input") or {},
                "result_preview": result_str[:300],
            })
            if on_event:
                await on_event(
                    "tool_result", {"name": tu["name"], "result_preview": result_str[:300]}
                )
            tool_result_blocks.append({
                "toolResult": {
                    "toolUseId": tu["toolUseId"],
                    "content": [{"text": result_str}],
                }
            })
        conv.append({"role": "user", "content": tool_result_blocks})

    return _result("")


async def call_bedrock_simple(
    model_id: str,
    api_key: str | None,
    system: str,
    messages: list[dict],
    on_event: ToolEventCallback | None = None,
) -> LLMResult:
    """Single-turn Bedrock Converse call without tools, streaming tokens."""
    _require_sdk()
    import os

    settings = get_settings()
    if api_key and not settings.aws_bedrock_use_iam_role:
        os.environ["AWS_BEARER_TOKEN_BEDROCK"] = api_key
    bedrock = boto3.client("bedrock-runtime", region_name=settings.aws_bedrock_region)

    conv = _to_bedrock_msgs(messages)
    request_body = {
        "modelId": model_id,
        "system": [{"text": system}],
        "messages": conv,
        "inferenceConfig": {"maxTokens": settings.max_tokens},
    }
    capture_request(request_body)
    result = await _stream_turn(bedrock, request_body, on_event)
    capture_response(result)
    usage = result["usage"] or {}
    content_blocks = result["content"]
    text_parts = [b["text"] for b in content_blocks if "text" in b]
    return LLMResult(
        text="\n".join(text_parts).strip(),
        input_tokens=usage.get("inputTokens", 0),
        output_tokens=usage.get("outputTokens", 0),
        cache_read_input_tokens=usage.get("cacheReadInputTokens", 0),
        cache_creation_input_tokens=usage.get("cacheWriteInputTokens", 0),
    )
