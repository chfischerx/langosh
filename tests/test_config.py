"""Tests for env-var > settings.json > default precedence in config.py."""

from __future__ import annotations

import pytest

from langosh import config as cfg
from langosh import settings as settings_module


@pytest.fixture
def clean_env(monkeypatch):
    """Strip every env var Langosh recognises before each test so the
    baseline is fully deterministic regardless of the shell."""
    for names in cfg.ENV_VARS.values():
        for n in names:
            monkeypatch.delenv(n, raising=False)
    yield monkeypatch


@pytest.fixture
def empty_settings_json(monkeypatch):
    """Force `_s.get` to return whatever default the caller passes,
    i.e. simulate an empty settings.json without touching the real one."""
    monkeypatch.setattr(settings_module, "_load", lambda: {})


@pytest.fixture
def populated_settings_json(monkeypatch):
    """Provide a settings.json stand-in with realistic values."""
    data = {
        "anthropic_api_key": "from-json",
        "default_provider": "openai",
        "default_model": "gpt-4o",
        "max_tokens": 2048,
        "aws_bedrock_use_iam_role": True,
    }
    monkeypatch.setattr(settings_module, "_load", lambda: dict(data))
    return data


class TestDefaults:
    def test_falls_back_to_built_in_default(self, clean_env, empty_settings_json):
        s = cfg.Settings()
        assert s.default_provider == "anthropic"
        assert s.anthropic_api_key == ""
        assert s.max_tokens == 4096
        assert s.max_tool_turns == 10
        assert s.aws_bedrock_region == "us-east-1"
        assert s.aws_bedrock_use_iam_role is False


class TestSettingsJson:
    def test_json_overrides_default(self, clean_env, populated_settings_json):
        s = cfg.Settings()
        assert s.anthropic_api_key == "from-json"
        assert s.default_provider == "openai"
        assert s.max_tokens == 2048
        assert s.aws_bedrock_use_iam_role is True


class TestEnvPrecedence:
    def test_env_wins_over_json(self, clean_env, populated_settings_json):
        clean_env.setenv("ANTHROPIC_API_KEY", "from-env")
        clean_env.setenv("LANGOSH_DEFAULT_PROVIDER", "anthropic")
        s = cfg.Settings()
        assert s.anthropic_api_key == "from-env"
        assert s.default_provider == "anthropic"
        # Untouched keys still come from json.
        assert s.max_tokens == 2048

    def test_empty_env_does_not_override(self, clean_env, populated_settings_json):
        # Exporting an empty string is typically a mistake ("unset but
        # exported"); don't let it clobber real values in settings.json.
        clean_env.setenv("ANTHROPIC_API_KEY", "")
        s = cfg.Settings()
        assert s.anthropic_api_key == "from-json"

    def test_aws_region_fallback_chain(self, clean_env, empty_settings_json):
        # AWS_BEDROCK_REGION wins over AWS_REGION when both are set.
        clean_env.setenv("AWS_REGION", "eu-west-1")
        clean_env.setenv("AWS_BEDROCK_REGION", "us-west-2")
        assert cfg.Settings().aws_bedrock_region == "us-west-2"

        clean_env.delenv("AWS_BEDROCK_REGION")
        assert cfg.Settings().aws_bedrock_region == "eu-west-1"


class TestEnvTypeParsing:
    def test_int_parses_from_env(self, clean_env, empty_settings_json):
        clean_env.setenv("LANGOSH_MAX_TOKENS", "8192")
        assert cfg.Settings().max_tokens == 8192

    def test_int_bad_env_falls_back(self, clean_env, populated_settings_json):
        # Garbage int in env should fall through to json rather than crash.
        clean_env.setenv("LANGOSH_MAX_TOKENS", "not-a-number")
        assert cfg.Settings().max_tokens == 2048

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("1", True),
            ("true", True),
            ("TRUE", True),
            ("yes", True),
            ("on", True),
            ("0", False),
            ("false", False),
            ("no", False),
            ("", False),  # empty env — treated as "unset", json/default wins
        ],
    )
    def test_bool_parsing(self, clean_env, empty_settings_json, raw, expected):
        clean_env.setenv("LANGOSH_AWS_BEDROCK_USE_IAM_ROLE", raw)
        assert cfg.Settings().aws_bedrock_use_iam_role is expected


class TestEnvOverrideFor:
    def test_returns_matching_env_name(self, clean_env):
        clean_env.setenv("ANTHROPIC_API_KEY", "abc")
        assert cfg.env_override_for("anthropic_api_key") == "ANTHROPIC_API_KEY"

    def test_returns_first_matching_name(self, clean_env):
        # AWS_BEDROCK_REGION takes precedence; make sure the reporting
        # reflects whichever one actually wins.
        clean_env.setenv("AWS_REGION", "eu-west-1")
        clean_env.setenv("AWS_BEDROCK_REGION", "us-west-2")
        assert cfg.env_override_for("aws_bedrock_region") == "AWS_BEDROCK_REGION"

    def test_returns_none_when_unset(self, clean_env):
        assert cfg.env_override_for("anthropic_api_key") is None

    def test_returns_none_for_unknown_key(self, clean_env):
        assert cfg.env_override_for("nope") is None
