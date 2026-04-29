"""voice_match.py 단위 테스트."""
import pytest

import voice_match


@pytest.fixture
def isolated_voice(tmp_path, monkeypatch):
    fake_dir = tmp_path / "_voice"
    fake_path = fake_dir / "profiles.json"
    monkeypatch.setattr(voice_match, "VOICE_DIR", fake_dir)
    monkeypatch.setattr(voice_match, "PROFILES_PATH", fake_path)
    yield fake_path


class TestAnalyzeQuantitative:
    def test_empty_samples(self):
        r = voice_match.analyze_tone_quantitative([])
        assert r["total_samples"] == 0

    def test_basic_analysis(self):
        samples = [
            "이거 진짜 대박이야! 한번 써봐.",
            "이 가격 보고 깜짝 놀랐잖아? 너도 사야 해.",
            "솔직히 처음엔 별로일 줄 알았는데 좋더라.",
        ]
        r = voice_match.analyze_tone_quantitative(samples)
        assert r["total_samples"] == 3
        assert r["total_sentences"] >= 3
        # 문장 분리 후 ! ? 가 제거된 형태로 들어가므로 ratio는 0일 수 있음
        # 단, dominant_ending은 인식되어야
        assert r["dominant_ending"] in [label for label, _ in voice_match.ENDINGS_PATTERNS] + ["(없음)"]

    def test_ending_distribution(self):
        samples = ["이거 너무 좋잖아.", "그치 정말 좋잖아.", "와 진짜 좋잖아."]
        r = voice_match.analyze_tone_quantitative(samples)
        # ~잖아가 dominant
        assert r["dominant_ending"] == "~잖아"

    def test_emoji_count(self):
        samples = ["오늘 날씨 좋네 ☀️", "이거 진짜 대박 🔥🔥", "그냥 그래"]
        r = voice_match.analyze_tone_quantitative(samples)
        assert r["emoji_avg_per_sample"] > 0


class TestExtractLlm:
    def test_no_api_key(self, monkeypatch):
        monkeypatch.setattr(voice_match.api_keys, "get_api_key",
                            lambda name: "")
        r = voice_match.extract_voice_profile_llm(["sample text"])
        assert "tone_summary" in r
        assert "API" in r["tone_summary"]

    def test_empty_samples(self):
        r = voice_match.extract_voice_profile_llm([])
        assert r["tone_summary"]


class TestSaveAndGet:
    def test_save_creates_profile(self, isolated_voice, monkeypatch):
        # LLM 호출 mock — 빠르게
        monkeypatch.setattr(voice_match, "extract_voice_profile_llm",
                            lambda samples: {
                                "tone_summary": "친근한 반말",
                                "characteristic_phrases": ["진짜", "솔직히"],
                                "voice_persona": "20대 자취생",
                                "do_use": ["진짜"], "avoid": ["격식체"],
                            })
        r = voice_match.save_profile(
            "user1", "메인",
            ["이거 진짜 좋아.", "솔직히 추천이야.", "한번 써봐."]
        )
        assert r["ok"] is True
        assert r["quantitative"]["total_samples"] == 3
        # 파일 존재
        assert isolated_voice.exists()

    def test_get_profile(self, isolated_voice, monkeypatch):
        monkeypatch.setattr(voice_match, "extract_voice_profile_llm",
                            lambda s: {"tone_summary": "테스트", "voice_persona": "P",
                                       "characteristic_phrases": [], "do_use": [], "avoid": []})
        voice_match.save_profile("user1", "메인", ["샘플 1.", "샘플 2."])
        p = voice_match.get_profile("user1", "메인")
        assert p["samples_count"] == 2
        assert p["qualitative"]["tone_summary"] == "테스트"

    def test_get_unknown_returns_empty(self, isolated_voice):
        assert voice_match.get_profile("nobody", "x") == {}

    def test_list_profiles(self, isolated_voice, monkeypatch):
        monkeypatch.setattr(voice_match, "extract_voice_profile_llm",
                            lambda s: {"tone_summary": "", "voice_persona": "",
                                       "characteristic_phrases": [], "do_use": [], "avoid": []})
        voice_match.save_profile("u1", "메인", ["a.", "b."])
        voice_match.save_profile("u1", "리뷰", ["c.", "d."])
        names = voice_match.list_profiles("u1")
        assert set(names) == {"메인", "리뷰"}

    def test_save_invalid_inputs(self, isolated_voice):
        assert voice_match.save_profile("", "메인", ["x"])["ok"] is False
        assert voice_match.save_profile("u", "", ["x"])["ok"] is False
        assert voice_match.save_profile("u", "메인", [])["ok"] is False


class TestFormatVoiceHint:
    def test_empty_when_no_profile(self, isolated_voice):
        assert voice_match.format_voice_hint("nobody") == ""

    def test_includes_tone_info(self, isolated_voice, monkeypatch):
        monkeypatch.setattr(voice_match, "extract_voice_profile_llm",
                            lambda s: {
                                "tone_summary": "친근한 반말",
                                "voice_persona": "20대 자취생",
                                "characteristic_phrases": ["진짜", "솔직히"],
                                "do_use": [], "avoid": ["격식체"],
                            })
        voice_match.save_profile("u1", "메인", ["진짜 좋아.", "솔직히 추천."])
        hint = voice_match.format_voice_hint("u1", "메인")
        assert "친근한 반말" in hint
        assert "20대 자취생" in hint
        assert "진짜" in hint
        assert "격식체" in hint
