"""script_judge.py 단위 테스트 — 폴백 모드 + 루프 로직 (LLM 미호출)."""
import pytest

import script_judge


@pytest.fixture
def no_api_key(monkeypatch):
    """LLM judge가 폴백 모드로 동작하도록."""
    monkeypatch.setattr(script_judge.api_keys, "get_api_key", lambda name: "")
    yield


class TestParseJudgeJson:
    def test_pure_json(self):
        s = '{"total": 80, "verdict": "PASS"}'
        d = script_judge._parse_judge_json(s)
        assert d == {"total": 80, "verdict": "PASS"}

    def test_json_in_markdown(self):
        s = '```json\n{"total": 75}\n```'
        d = script_judge._parse_judge_json(s)
        assert d == {"total": 75}

    def test_no_json_returns_none(self):
        assert script_judge._parse_judge_json("just plain text") is None


class TestFallbackJudge:
    def test_short_weak_script_fails(self, no_api_key):
        r = script_judge.judge_script("짧은 글", product="x", category="general")
        assert r["ok"] is False  # 폴백 표시
        assert r["passed"] is False
        assert r["total"] < 80

    def test_long_with_cta_partially_passes(self, no_api_key):
        # CTA + Hook 단어 + 적절 길이
        text = ("이거 진짜 신기한 제품이에요? 이거 한번 써보세요. " * 3 +
                "쿠팡 설명란에 링크 있어요. 지금 클릭해서 확인하세요.")
        r = script_judge.judge_script(text, product="제품X", category="general")
        assert r["scores"]["cta_clarity"]["score"] >= 15  # CTA 단어 다수
        assert r["scores"]["hook_impact"]["score"] >= 10  # 의문문 + 단어

    def test_returns_5_dimensions(self, no_api_key):
        r = script_judge.judge_script("test", product="x", category="general")
        for k in ("hook_impact", "category_fit", "length_fit",
                  "cta_clarity", "conversion_power"):
            assert k in r["scores"]
            assert "score" in r["scores"][k]
            assert "reason" in r["scores"][k]

    def test_total_in_range(self, no_api_key):
        r = script_judge.judge_script("any text", product="", category="")
        assert 0 <= r["total"] <= 100


class TestQualityLoop:
    def test_passes_immediately_when_score_high(self, no_api_key, monkeypatch):
        # judge가 항상 PASS 반환하도록 monkeypatch
        monkeypatch.setattr(script_judge, "judge_script",
                            lambda *a, **kw: {"ok": True, "total": 90, "passed": True,
                                              "verdict": "PASS", "scores": {},
                                              "improvement": ""})
        result = script_judge.generate_with_quality_loop(
            lambda h="": "any script", product="x", category="y", min_score=80
        )
        assert result["attempts"] == 1
        assert result["passed"] is True

    def test_retries_until_max_attempts(self, no_api_key, monkeypatch):
        # judge가 항상 FAIL 반환 → 최대 시도까지 가야 함
        monkeypatch.setattr(script_judge, "judge_script",
                            lambda *a, **kw: {"ok": True, "total": 50, "passed": False,
                                              "verdict": "FAIL", "scores": {},
                                              "improvement": "더 짧게"})
        result = script_judge.generate_with_quality_loop(
            lambda h="": "weak", product="x", category="y", min_score=80, max_attempts=3
        )
        assert result["attempts"] == 3
        assert result["passed"] is False
        assert len(result["history"]) == 3

    def test_keeps_best_attempt(self, no_api_key, monkeypatch):
        scores_seq = [40, 75, 60]
        idx = [0]

        def mock_judge(*a, **kw):
            i = idx[0]
            idx[0] += 1
            return {"ok": True, "total": scores_seq[i], "passed": False,
                    "verdict": "FAIL", "scores": {}, "improvement": ""}
        monkeypatch.setattr(script_judge, "judge_script", mock_judge)

        result = script_judge.generate_with_quality_loop(
            lambda h="": f"v{idx[0]}", product="x", category="y",
            min_score=80, max_attempts=3
        )
        # 최고 점수 75인 attempt 2가 채택돼야
        assert result["judge"]["total"] == 75

    def test_passes_on_second_attempt(self, no_api_key, monkeypatch):
        scores_seq = [40, 85]
        idx = [0]

        def mock_judge(*a, **kw):
            i = idx[0]
            idx[0] += 1
            s = scores_seq[i]
            return {"ok": True, "total": s, "passed": s >= 80,
                    "verdict": "PASS" if s >= 80 else "FAIL",
                    "scores": {}, "improvement": "더 강한 hook"}
        monkeypatch.setattr(script_judge, "judge_script", mock_judge)

        result = script_judge.generate_with_quality_loop(
            lambda h="": "v", product="x", category="y", min_score=80, max_attempts=5
        )
        assert result["attempts"] == 2  # PASS 즉시 종료
        assert result["passed"] is True
        assert result["judge"]["total"] == 85

    def test_generate_fn_receives_improvement_hint(self, no_api_key, monkeypatch):
        captured_hints = []

        def gen(hint=""):
            captured_hints.append(hint)
            return "any"

        monkeypatch.setattr(script_judge, "judge_script",
                            lambda *a, **kw: {"ok": True, "total": 50, "passed": False,
                                              "verdict": "FAIL", "scores": {},
                                              "improvement": "TEST_HINT_XYZ"})
        script_judge.generate_with_quality_loop(
            gen, product="x", category="y", min_score=80, max_attempts=2
        )
        # 첫 시도는 빈 hint, 두 번째는 직전 improvement
        assert captured_hints[0] == ""
        assert "TEST_HINT_XYZ" in captured_hints[1]
