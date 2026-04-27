"""api_keys.py 단위 테스트."""
import pytest

import api_keys


@pytest.fixture
def clean_env(monkeypatch):
    """테스트용 환경변수 격리."""
    for k in ("ANTHROPIC_API_KEY", "PEXELS_API_KEY", "TEST_KEY_X"):
        monkeypatch.delenv(k, raising=False)
    yield


class TestGetApiKey:
    def test_missing_returns_empty_string(self, clean_env):
        assert api_keys.get_api_key("NONEXISTENT_KEY_XYZ") == ""

    def test_env_var_fallback(self, clean_env, monkeypatch):
        monkeypatch.setenv("TEST_KEY_X", "secret-value")
        assert api_keys.get_api_key("TEST_KEY_X") == "secret-value"

    def test_returns_string_not_none(self, clean_env):
        result = api_keys.get_api_key("NEVER_SET")
        assert isinstance(result, str)


class TestHasKey:
    def test_missing_is_false(self, clean_env):
        assert api_keys.has_key("NONEXISTENT_KEY_XYZ") is False

    def test_present_is_true(self, clean_env, monkeypatch):
        monkeypatch.setenv("TEST_KEY_X", "anything")
        assert api_keys.has_key("TEST_KEY_X") is True

    def test_empty_string_is_false(self, clean_env, monkeypatch):
        monkeypatch.setenv("TEST_KEY_X", "")
        assert api_keys.has_key("TEST_KEY_X") is False
