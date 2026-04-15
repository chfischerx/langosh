"""Dynamic model catalog — fetches available models from provider APIs."""

import asyncio
import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

_OPENAI_EXCLUDE = {"dall-e", "whisper", "tts", "text-embedding", "davinci", "babbage"}


def _is_openai_chat_model(model_id: str) -> bool:
    """Filter OpenAI models to chat-capable ones only."""
    lower = model_id.lower()
    if any(lower.startswith(prefix) for prefix in _OPENAI_EXCLUDE):
        return False
    return any(lower.startswith(p) for p in ("gpt-", "o1", "o3", "o4", "chatgpt-"))


@dataclass
class ModelInfo:
    """Single model entry."""

    id: str
    name: str
    provider: str


PROVIDER_CONFIGS: dict[str, dict] = {
    "anthropic": {
        "url": "https://api.anthropic.com/v1/models",
        "headers_fn": lambda key: {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
        },
        "parse_fn": lambda data: [
            ModelInfo(id=m["id"], name=m.get("display_name", m["id"]), provider="anthropic")
            for m in data.get("data", [])
            if m.get("type") == "model"
        ],
    },
    "openai": {
        "url": "https://api.openai.com/v1/models",
        "headers_fn": lambda key: {"Authorization": f"Bearer {key}"},
        "parse_fn": lambda data: [
            ModelInfo(id=m["id"], name=m["id"], provider="openai")
            for m in data.get("data", [])
            if m.get("id") and _is_openai_chat_model(m["id"])
        ],
    },
    "bedrock_converse": {"custom_fetch": True},
}


def _parse_bedrock_foundation(model_summaries: list[dict]) -> list[ModelInfo]:
    """Filter Bedrock ListFoundationModels to on-demand text models."""
    return [
        ModelInfo(
            id=m["modelId"],
            name=m.get("modelName", m["modelId"]),
            provider="bedrock_converse",
        )
        for m in model_summaries
        if "ON_DEMAND" in m.get("inferenceTypesSupported", [])
        and "TEXT" in m.get("outputModalities", [])
    ]


def _parse_bedrock_profiles(profile_summaries: list[dict]) -> list[ModelInfo]:
    """Filter Bedrock ListInferenceProfiles to active profiles."""
    return [
        ModelInfo(
            id=p["inferenceProfileId"],
            name=p.get("inferenceProfileName", p["inferenceProfileId"]),
            provider="bedrock_converse",
        )
        for p in profile_summaries
        if p.get("status") == "ACTIVE"
    ]


async def _fetch_provider(provider: str, api_key: str) -> list[ModelInfo]:
    """Fetch models from a single provider's HTTP API."""
    config = PROVIDER_CONFIGS[provider]
    url = config["url"]
    headers = config["headers_fn"](api_key)

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    models = config["parse_fn"](data)
    models.sort(key=lambda m: m.id)
    return models


async def _fetch_bedrock(region: str, use_iam_role: bool, api_key: str | None) -> list[ModelInfo]:
    """Fetch Bedrock foundation models + inference profiles via boto3."""
    try:
        import boto3
    except ImportError:
        logger.warning("boto3 not installed, skipping Bedrock model fetch")
        return []

    def _fetch_sync() -> list[ModelInfo]:
        client = boto3.client("bedrock", region_name=region)
        foundation: list[ModelInfo] = []
        profiles: list[ModelInfo] = []
        try:
            fm = client.list_foundation_models()
            foundation = _parse_bedrock_foundation(fm.get("modelSummaries", []))
        except Exception as e:
            logger.warning(f"Bedrock ListFoundationModels failed: {e}")
        try:
            ip = client.list_inference_profiles()
            profiles = _parse_bedrock_profiles(ip.get("inferenceProfileSummaries", []))
        except Exception as e:
            logger.warning(f"Bedrock ListInferenceProfiles failed: {e}")
        merged = foundation + profiles
        merged.sort(key=lambda m: m.id)
        return merged

    if api_key and not use_iam_role:
        import os

        os.environ["AWS_BEARER_TOKEN_BEDROCK"] = api_key

    return await asyncio.to_thread(_fetch_sync)


async def fetch_models(
    providers: set[str] | None = None,
) -> dict[str, list[ModelInfo]]:
    """Fetch available models from all configured providers in parallel.

    Only fetches from providers that have API keys set.
    Optionally filter to a specific set of providers.
    """
    from ..config import get_settings

    settings = get_settings()

    # Build map of provider -> api_key for configured providers
    configured: dict[str, str | None] = {}
    if settings.anthropic_api_key:
        configured["anthropic"] = settings.anthropic_api_key
    if settings.openai_api_key:
        configured["openai"] = settings.openai_api_key
    # Bedrock always included — boto3 picks up credentials from
    # ~/.aws/config, env vars, IAM role, or instance profile.
    configured.setdefault("bedrock_converse", None)

    # Claude SDK always included — same models as Anthropic, no API key needed
    configured.setdefault("claude_sdk", None)

    if providers:
        configured = {k: v for k, v in configured.items() if k in providers}

    # Build fetch tasks
    tasks: dict[str, asyncio.Task] = {}
    for provider, api_key in configured.items():
        if provider == "claude_sdk":
            # Reuse Anthropic API to get model list (needs key), or fall back to static
            if settings.anthropic_api_key:
                tasks[provider] = asyncio.ensure_future(
                    _fetch_provider("anthropic", settings.anthropic_api_key)
                )
            # else: handled below as static fallback
        elif provider == "bedrock_converse":
            tasks[provider] = asyncio.ensure_future(
                _fetch_bedrock(settings.aws_bedrock_region, settings.aws_bedrock_use_iam_role, api_key)
            )
        else:
            tasks[provider] = asyncio.ensure_future(_fetch_provider(provider, api_key or ""))

    results: dict[str, list[ModelInfo]] = {}

    for provider, task in tasks.items():
        try:
            models = await task
            if models:
                if provider == "claude_sdk":
                    # Remap provider from "anthropic" to "claude_sdk"
                    models = [ModelInfo(id=m.id, name=m.name, provider="claude_sdk") for m in models]
                results[provider] = models
        except Exception as e:
            logger.warning(f"Failed to fetch models for {provider}: {e}")

    # Static fallback for claude_sdk if no Anthropic API key
    if "claude_sdk" in configured and "claude_sdk" not in results:
        results["claude_sdk"] = [
            ModelInfo(id="claude-opus-4-6", name="Claude Opus 4.6", provider="claude_sdk"),
            ModelInfo(id="claude-sonnet-4-6", name="Claude Sonnet 4.6", provider="claude_sdk"),
            ModelInfo(id="claude-haiku-4-5-20251001", name="Claude Haiku 4.5", provider="claude_sdk"),
        ]

    return results
