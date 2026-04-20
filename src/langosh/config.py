"""Application configuration.

Resolution order for every setting:

    exported env var  >  ~/.langosh/settings.json  >  built-in default

Env vars are read live at property access — `export FOO=bar` in your
shell before launching `langosh` is the supported override mechanism.
"""

from __future__ import annotations

import os

from . import settings as _s

DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-sonnet-4-20250514",
    "openai": "gpt-4o",
    "deepseek": "deepseek-chat",
    "xai": "grok-3-latest",
    "bedrock_converse": "us.anthropic.claude-sonnet-4-20250514-v1:0",
    "claude_sdk": "claude-sonnet-4-6",
}

# Defaults for settings that have non-empty fallbacks
_DEFAULTS: dict[str, object] = {
    "default_provider": "anthropic",
    "default_model": "",
    "anthropic_api_key": "",
    "openai_api_key": "",
    "aws_bedrock_region": "us-east-1",
    "aws_bedrock_use_iam_role": False,
    "max_tokens": 4096,
    "max_tool_turns": 10,
}

# settings-key -> (env var names, tried in order). The first non-empty
# env var wins. Unprefixed names (ANTHROPIC_API_KEY, OPENAI_API_KEY,
# AWS_REGION) match what the upstream SDKs already read, so a single
# export picks up both the SDK and Langosh. Everything else is
# LANGOSH_-prefixed to stay out of other tools' namespace.
ENV_VARS: dict[str, tuple[str, ...]] = {
    "anthropic_api_key": ("ANTHROPIC_API_KEY",),
    "openai_api_key": ("OPENAI_API_KEY",),
    "default_provider": ("LANGOSH_DEFAULT_PROVIDER",),
    "default_model": ("LANGOSH_DEFAULT_MODEL",),
    "aws_bedrock_region": ("AWS_BEDROCK_REGION", "AWS_REGION"),
    "aws_bedrock_use_iam_role": ("LANGOSH_AWS_BEDROCK_USE_IAM_ROLE",),
    "max_tokens": ("LANGOSH_MAX_TOKENS",),
    "max_tool_turns": ("LANGOSH_MAX_TOOL_TURNS",),
}


def _env_lookup(key: str) -> str | None:
    """Return the first non-empty env var for `key`, or None."""
    for name in ENV_VARS.get(key, ()):
        val = os.environ.get(name)
        if val not in (None, ""):
            return val
    return None


def _as_bool(val: str) -> bool:
    return val.strip().lower() in ("1", "true", "yes", "on")


def env_override_for(key: str) -> str | None:
    """Return the env var name currently overriding `key`, else None.

    Used by `/settings show` to annotate values that came from env rather
    than settings.json.
    """
    for name in ENV_VARS.get(key, ()):
        val = os.environ.get(name)
        if val not in (None, ""):
            return name
    return None


class Settings:
    """Read-only view with precedence env > settings.json > default."""

    def _str(self, key: str) -> str:
        env = _env_lookup(key)
        if env is not None:
            return env
        return _s.get(key, _DEFAULTS[key])

    def _int(self, key: str) -> int:
        env = _env_lookup(key)
        if env is not None:
            try:
                return int(env)
            except ValueError:
                pass  # fall through to settings.json / default
        return int(_s.get(key, _DEFAULTS[key]))

    def _bool(self, key: str) -> bool:
        env = _env_lookup(key)
        if env is not None:
            return _as_bool(env)
        return bool(_s.get(key, _DEFAULTS[key]))

    @property
    def default_provider(self) -> str:
        return self._str("default_provider")

    @property
    def default_model(self) -> str:
        return self._str("default_model")

    @property
    def anthropic_api_key(self) -> str:
        return self._str("anthropic_api_key")

    @property
    def openai_api_key(self) -> str:
        return self._str("openai_api_key")

    @property
    def aws_bedrock_region(self) -> str:
        return self._str("aws_bedrock_region")

    @property
    def aws_bedrock_use_iam_role(self) -> bool:
        return self._bool("aws_bedrock_use_iam_role")

    @property
    def max_tokens(self) -> int:
        return self._int("max_tokens")

    @property
    def max_tool_turns(self) -> int:
        return self._int("max_tool_turns")


# Singleton — no caching needed, each property reads the file fresh
_settings = Settings()


def get_settings() -> Settings:
    return _settings
