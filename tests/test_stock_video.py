"""stock_video.py 단위 테스트 — API 키 없을 때 동작 (네트워크 호출 없음)."""
import pytest

import stock_video


@pytest.fixture
def no_keys(monkeypatch):
    """모든 외부 키 제거."""
    monkeypatch.setattr(stock_video.api_keys, "get_api_key", lambda name: "")
    yield


class TestSearchPexels:
    def test_no_key_returns_empty_list(self, no_keys):
        assert stock_video.search_pexels("배수구") == []

    def test_returns_list_type(self, no_keys):
        result = stock_video.search_pexels("test")
        assert isinstance(result, list)


class TestDownloadVideo:
    def test_empty_url_returns_false(self):
        assert stock_video.download_video("", "/tmp/x") is False

    def test_invalid_url_returns_false(self, tmp_path):
        # 잘못된 URL → False (raise 안 함)
        result = stock_video.download_video("not-a-url", str(tmp_path / "x.mp4"))
        assert result is False
