"""AWS Bedrock Converse multi-turn tool-calling loop with prompt caching."""

import asyncio
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
    """Multi-turn Bedrock Converse call with tool-use and prompt caching."""
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
        resp = await asyncio.to_thread(bedrock.converse, **request_body)
        capture_response(resp)
        usage = resp.get("usage", {})
        total_input += usage.get("inputTokens", 0)
        total_output += usage.get("outputTokens", 0)
        total_cache_read += usage.get("cacheReadInputTokens", 0)
        total_cache_write += usage.get("cacheWriteInputTokens", 0)

        stop_reason = resp.get("stopReason", "")
        output = resp.get("output", {})
        msg = output.get("message", {})
        content_blocks = msg.get("content", [])

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
) -> LLMResult:
    """Single-turn Bedrock Converse call without tools."""
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
    resp = await asyncio.to_thread(bedrock.converse, **request_body)
    capture_response(resp)
    usage = resp.get("usage", {})
    output = resp.get("output", {})
    msg = output.get("message", {})
    content_blocks = msg.get("content", [])
    text_parts = [b["text"] for b in content_blocks if "text" in b]
    return LLMResult(
        text="\n".join(text_parts).strip(),
        input_tokens=usage.get("inputTokens", 0),
        output_tokens=usage.get("outputTokens", 0),
    )
