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


# Curated fallback catalogs. Used when the CLI lacks credentials to
# query a provider's live list — users often run the CLI against a
# backend that has different keys than their local machine, so every
# supported provider must still appear in the picker.
STATIC_MODELS: dict[str, list[ModelInfo]] = {
    "anthropic": [
        ModelInfo(id="claude-opus-4-5-20251101", name="Claude Opus 4.5", provider="anthropic"),
        ModelInfo(id="claude-sonnet-4-5-20250929", name="Claude Sonnet 4.5", provider="anthropic"),
        ModelInfo(id="claude-haiku-4-5-20251001", name="Claude Haiku 4.5", provider="anthropic"),
        ModelInfo(id="claude-3-5-sonnet-20241022", name="Claude 3.5 Sonnet (2024-10-22)", provider="anthropic"),
        ModelInfo(id="claude-3-5-haiku-20241022", name="Claude 3.5 Haiku", provider="anthropic"),
    ],
    "openai": [
        ModelInfo(id="gpt-4o", name="GPT-4o", provider="openai"),
        ModelInfo(id="gpt-4o-mini", name="GPT-4o mini", provider="openai"),
        ModelInfo(id="gpt-4-turbo", name="GPT-4 Turbo", provider="openai"),
        ModelInfo(id="o1", name="o1", provider="openai"),
        ModelInfo(id="o1-mini", name="o1-mini", provider="openai"),
        ModelInfo(id="o3-mini", name="o3-mini", provider="openai"),
    ],
    "bedrock_converse": [
        ModelInfo(
            id="global.anthropic.claude-sonnet-4-5-20250929-v1:0",
            name="Global Claude Sonnet 4.5",
            provider="bedrock_converse",
        ),
        ModelInfo(
            id="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
            name="US Claude Sonnet 4.5",
            provider="bedrock_converse",
        ),
        ModelInfo(
            id="global.anthropic.claude-opus-4-5-20251101-v1:0",
            name="Global Claude Opus 4.5",
            provider="bedrock_converse",
        ),
        ModelInfo(
            id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
            name="US Claude Haiku 4.5",
            provider="bedrock_converse",
        ),
        ModelInfo(
            id="anthropic.claude-3-5-sonnet-20240620-v1:0",
            name="Claude 3.5 Sonnet (Bedrock 2024-06-20)",
            provider="bedrock_converse",
        ),
        ModelInfo(
            id="amazon.nova-pro-v1:0",
            name="Amazon Nova Pro",
            provider="bedrock_converse",
        ),
    ],
    "claude_sdk": [
        ModelInfo(id="claude-opus-4-6", name="Claude Opus 4.6", provider="claude_sdk"),
        ModelInfo(id="claude-sonnet-4-6", name="Claude Sonnet 4.6", provider="claude_sdk"),
        ModelInfo(id="claude-haiku-4-5-20251001", name="Claude Haiku 4.5", provider="claude_sdk"),
    ],
}

# Every provider the CLI + generated graphs support. The catalog always
# includes all of these; static entries fill in when live fetches fail.
SUPPORTED_PROVIDERS = tuple(STATIC_MODELS.keys())


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
    """Fetch available models from every supported provider in parallel.

    For each provider we try a live API fetch when the CLI has the
    credentials for it. When no key is available — or the live fetch
    fails — we fall back to `STATIC_MODELS[provider]`. This way the
    picker shows a useful catalog even when the CLI itself has no
    keys (the backend running the deployed graph may have them).

    `providers` optionally restricts to a subset of supported
    providers.
    """
    from ..config import get_settings

    settings = get_settings()

    targets = set(SUPPORTED_PROVIDERS)
    if providers:
        targets &= providers

    # Build fetch tasks — only for providers we can hit without keys or
    # have keys for. Providers with no key path skip to static fallback.
    tasks: dict[str, asyncio.Task] = {}
    for provider in targets:
        if provider == "anthropic":
            if settings.anthropic_api_key:
                tasks[provider] = asyncio.ensure_future(
                    _fetch_provider("anthropic", settings.anthropic_api_key)
                )
        elif provider == "openai":
            if settings.openai_api_key:
                tasks[provider] = asyncio.ensure_future(
                    _fetch_provider("openai", settings.openai_api_key)
                )
        elif provider == "bedrock_converse":
            # boto3 may pick up credentials from env / ~/.aws / IAM role.
            tasks[provider] = asyncio.ensure_future(
                _fetch_bedrock(
                    settings.aws_bedrock_region,
                    settings.aws_bedrock_use_iam_role,
                    None,
                )
            )
        elif provider == "claude_sdk":
            # Reuse Anthropic API to enumerate Claude SDK-compatible
            # models when we have an Anthropic key; else fall back.
            if settings.anthropic_api_key:
                tasks[provider] = asyncio.ensure_future(
                    _fetch_provider("anthropic", settings.anthropic_api_key)
                )

    results: dict[str, list[ModelInfo]] = {}
    for provider, task in tasks.items():
        try:
            models = await task
            if models:
                if provider == "claude_sdk":
                    models = [
                        ModelInfo(id=m.id, name=m.name, provider="claude_sdk")
                        for m in models
                    ]
                results[provider] = models
        except Exception as e:
            logger.warning(f"Failed to fetch models for {provider}: {e}")

    # Fill any gaps with the curated static catalog so every supported
    # provider shows up in the picker.
    for provider in targets:
        if provider not in results and provider in STATIC_MODELS:
            results[provider] = list(STATIC_MODELS[provider])

    return results
