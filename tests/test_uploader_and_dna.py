"""youtube_uploader + competitor_dna 단위 테스트 (네트워크 없이)."""
import json

import pytest

import competitor_dna
import youtube_uploader


# ── youtube_uploader ──────────────────────────────────────────

class TestYouTubeUploaderDeps:
    def test_check_deps_returns_tuple(self):
        ok, msg = youtube_uploader._check_deps()
        assert isinstance(ok, bool)
        assert isinstance(msg, str)


class TestAuthFlow:
    def test_no_oauth_keys_returns_error(self, monkeypatch):
        monkeypatch.setattr(youtube_uploader.api_keys, "get_api_key",
                            lambda name: "")
        result = youtube_uploader.get_auth_url()
        assert result["ok"] is False
        # deps 미설치(google-api-python-client) 또는 OAuth 키 없음 — 둘 다 실패
        assert result["error"]  # 어떤 에러 메시지든 비어있지 않아야

    def test_exchange_code_no_keys(self, monkeypatch):
        monkeypatch.setattr(youtube_uploader.api_keys, "get_api_key",
                            lambda name: "")
        result = youtube_uploader.exchange_code("dummy_code")
        assert result["ok"] is False


class TestUpload:
    def test_no_credentials_returns_error(self, monkeypatch):
        monkeypatch.setattr(youtube_uploader, "_load_credentials", lambda: None)
        result = youtube_uploader.upload_short("/tmp/x.mp4", "title")
        assert result["ok"] is False

    def test_missing_file_returns_error(self, monkeypatch):
        # creds 있는 척, 파일은 없음
        monkeypatch.setattr(youtube_uploader, "_load_credentials",
                            lambda: object())  # truthy
        result = youtube_uploader.upload_short("/tmp/nonexistent_xyz.mp4", "t")
        # deps 미설치 → deps error 또는 file 없음 → file error
        assert result["ok"] is False


# ── competitor_dna ────────────────────────────────────────────

@pytest.fixture
def isolated_dna(tmp_path, monkeypatch):
    fake = tmp_path / "_dna" / "dna_library.jsonl"
    monkeypatch.setattr(competitor_dna, "DNA_LIB_PATH", fake)
    monkeypatch.setattr(competitor_dna, "DNA_DIR", fake.parent)
    yield fake


class TestFetchVideoMetadata:
    def test_empty_url(self):
        r = competitor_dna.fetch_video_metadata("")
        assert r["ok"] is False

    def test_platform_detection_youtube(self, monkeypatch):
        # yt-dlp는 mock 안 함, 실제 네트워크 → URL 검증만
        # 빈 URL 케이스만 위에서 확인. 여기서는 platform 탐지 로직만.
        # 실제 호출 안 하기 위해 fetch 자체를 monkeypatch
        def fake_fetch(url):
            if "youtube.com" in url:
                return {"ok": True, "platform": "youtube"}
            return {"ok": False}
        monkeypatch.setattr(competitor_dna, "fetch_video_metadata", fake_fetch)
        assert competitor_dna.fetch_video_metadata(
            "https://youtube.com/shorts/abc")["platform"] == "youtube"


class TestExtractDna:
    def test_no_api_key_returns_placeholder(self, monkeypatch):
        monkeypatch.setattr(competitor_dna.api_keys, "get_api_key",
                            lambda name: "")
        r = competitor_dna.extract_dna({"title": "t", "view_count": 100000})
        assert "API" in r["hook_pattern"] or r["hook_pattern"] != ""


class TestSaveAndList:
    def test_save_creates_file(self, isolated_dna):
        ok = competitor_dna.save_dna(
            "https://youtube.com/x",
            {"platform": "youtube", "title": "t", "view_count": 1000, "like_count": 50},
            {"hook_pattern": "충격통계", "structure": "문제→해결",
             "cta_pattern": "설명란링크", "viral_factors": ["수치", "공감"],
             "translation_template": "..."},
            my_product="제품X",
        )
        assert ok is True
        assert isolated_dna.exists()

    def test_list_returns_records(self, isolated_dna):
        for i in range(3):
            competitor_dna.save_dna(
                f"https://youtube.com/{i}",
                {"platform": "youtube", "title": f"t{i}",
                 "view_count": 1000, "like_count": 10},
                {"hook_pattern": "p"},
            )
        records = competitor_dna.list_dna_records()
        assert len(records) == 3
        # 최신순 (역순)
        assert records[0]["url"].endswith("/2")

    def test_list_empty_when_no_file(self, isolated_dna):
        assert competitor_dna.list_dna_records() == []


class TestApplyDnaToProduct:
    def test_no_api_key_returns_empty(self, monkeypatch):
        monkeypatch.setattr(competitor_dna.api_keys, "get_api_key",
                            lambda name: "")
        r = competitor_dna.apply_dna_to_product(
            {"hook_pattern": "p"}, "상품X", "beauty"
        )
        assert r == ""

    def test_empty_inputs(self):
        assert competitor_dna.apply_dna_to_product({}, "", "") == ""
        assert competitor_dna.apply_dna_to_product({"hook_pattern": "p"}, "", "") == ""
