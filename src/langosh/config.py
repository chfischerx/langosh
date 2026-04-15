"""Application configuration loaded from environment variables and .env files."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-sonnet-4-20250514",
    "openai": "gpt-4o",
    "deepseek": "deepseek-chat",
    "xai": "grok-3-latest",
    "bedrock_converse": "us.anthropic.claude-sonnet-4-20250514-v1:0",
    "claude_sdk": "claude-sonnet-4-6",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    default_provider: str = "anthropic"
    default_model: str = ""

    anthropic_api_key: str = ""
    openai_api_key: str = ""

    aws_bedrock_region: str = "us-east-1"
    aws_bedrock_use_iam_role: bool = False

    max_tokens: int = 4096
    max_tool_turns: int = 10


@lru_cache
def get_settings() -> Settings:
    return Settings()
