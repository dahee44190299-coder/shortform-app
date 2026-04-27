"""llm.py 단위 테스트 — call_claude/translate (네트워크 호출 없이)."""
import pytest

import llm


@pytest.fixture
def no_anthropic_key(monkeypatch):
    """ANTHROPIC_API_KEY가 없는 상태."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(llm.api_keys, "get_api_key",
                        lambda name: "" if name == "ANTHROPIC_API_KEY" else "")
    yield


class TestCallClaude:
    def test_no_key_returns_none(self, no_anthropic_key):
        result = llm.call_claude("system", "user")
        assert result is None

    def test_no_key_does_not_call_on_error(self, no_anthropic_key):
        called = []
        llm.call_claude("s", "u", on_error=lambda e: called.append(e))
        # API 키가 없는 건 정상 분기 → on_error 호출되면 안 됨
        assert called == []


class TestTranslateKeyword:
    def test_empty_returns_empty(self):
        assert llm.translate_keyword_to_english("") == ""

    def test_already_english_passthrough(self):
        assert llm.translate_keyword_to_english("running shoes") == "running shoes"
        assert llm.translate_keyword_to_english("4K-monitor 2024") == "4K-monitor 2024"

    def test_korean_no_key_returns_original(self, no_anthropic_key):
        # 키가 없으면 call_claude가 None 반환 → 원본 그대로
        assert llm.translate_keyword_to_english("배수구 청소") == "배수구 청소"
