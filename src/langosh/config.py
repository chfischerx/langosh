"""Application configuration — reads from ~/.langosh/settings.json."""

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
_DEFAULTS = {
    "default_provider": "anthropic",
    "default_model": "",
    "anthropic_api_key": "",
    "openai_api_key": "",
    "aws_bedrock_region": "us-east-1",
    "aws_bedrock_use_iam_role": False,
    "max_tokens": 4096,
    "max_tool_turns": 10,
}


class Settings:
    """Read-only view over ~/.langosh/settings.json with typed defaults."""

    @property
    def default_provider(self) -> str:
        return _s.get("default_provider", _DEFAULTS["default_provider"])

    @property
    def default_model(self) -> str:
        return _s.get("default_model", _DEFAULTS["default_model"])

    @property
    def anthropic_api_key(self) -> str:
        return _s.get("anthropic_api_key", _DEFAULTS["anthropic_api_key"])

    @property
    def openai_api_key(self) -> str:
        return _s.get("openai_api_key", _DEFAULTS["openai_api_key"])

    @property
    def aws_bedrock_region(self) -> str:
        return _s.get("aws_bedrock_region", _DEFAULTS["aws_bedrock_region"])

    @property
    def aws_bedrock_use_iam_role(self) -> bool:
        return _s.get("aws_bedrock_use_iam_role", _DEFAULTS["aws_bedrock_use_iam_role"])

    @property
    def max_tokens(self) -> int:
        return int(_s.get("max_tokens", _DEFAULTS["max_tokens"]))

    @property
    def max_tool_turns(self) -> int:
        return int(_s.get("max_tool_turns", _DEFAULTS["max_tool_turns"]))


# Singleton — no caching needed, each property reads the file fresh
_settings = Settings()


def get_settings() -> Settings:
    return _settings
