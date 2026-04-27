"""regeneration.py 단위 테스트 — Phase 1-C 저성과 영상 자동 감지."""
from datetime import datetime, timezone, timedelta

import regeneration


def _record(video_id="v1", title="t", hook_type="problem",
            clicks=0, age_hours=30):
    created = (datetime.now(timezone.utc) - timedelta(hours=age_hours)).isoformat()
    return {
        "video_id": video_id, "title": title, "hook_type": hook_type,
        "manual_clicks": clicks, "created_at": created,
    }


class TestIsUnderperforming:
    def test_old_with_zero_clicks_is_under(self):
        assert regeneration.is_underperforming(_record(age_hours=30, clicks=0)) is True

    def test_recent_video_skipped(self):
        # 12시간밖에 안 됨 → 판단 보류 (False)
        assert regeneration.is_underperforming(_record(age_hours=12, clicks=0)) is False

    def test_old_with_clicks_is_not_under(self):
        assert regeneration.is_underperforming(_record(age_hours=30, clicks=5)) is False

    def test_missing_created_at(self):
        assert regeneration.is_underperforming({"manual_clicks": 0}) is False

    def test_invalid_date(self):
        assert regeneration.is_underperforming(
            {"created_at": "not-a-date", "manual_clicks": 0}
        ) is False

    def test_custom_threshold(self):
        # max_clicks=2 → 클릭 2회까지는 under
        assert regeneration.is_underperforming(
            _record(age_hours=30, clicks=2), max_clicks=2
        ) is True
        assert regeneration.is_underperforming(
            _record(age_hours=30, clicks=3), max_clicks=2
        ) is False


class TestFindUnderperforming:
    def test_filters_correctly(self):
        recs = [
            _record(video_id="v1", clicks=0, age_hours=30),  # under
            _record(video_id="v2", clicks=5, age_hours=30),  # not under
            _record(video_id="v3", clicks=0, age_hours=12),  # too recent
            _record(video_id="v4", clicks=0, age_hours=48),  # under
        ]
        under = regeneration.find_underperforming(recs)
        ids = [r["video_id"] for r in under]
        assert ids == ["v1", "v4"]


class TestSuggestAlternativeHook:
    def test_returns_different_pattern(self):
        alt = regeneration.suggest_alternative_hook("problem")
        assert alt["id"] != "problem"
        assert "label" in alt and "hint" in alt

    def test_unknown_input_still_returns(self):
        alt = regeneration.suggest_alternative_hook("nonexistent")
        assert alt["id"] in [p[0] for p in regeneration.HOOK_PATTERNS]


class TestMakeRegenerationPrompt:
    def test_includes_title_and_alt_hint(self):
        rec = _record(title="배수구 냄새 끝", hook_type="problem")
        prompt = regeneration.make_regeneration_prompt(rec, "원본 스크립트 샘플")
        assert "배수구 냄새 끝" in prompt
        assert "JSON" in prompt
        # 원본 hook_type 'problem' → 다른 패턴이 추천되어야
        alt = regeneration.suggest_alternative_hook("problem")
        assert alt["label"] in prompt

    def test_no_script_variant(self):
        rec = _record(title="제목")
        prompt = regeneration.make_regeneration_prompt(rec)
        assert "참고할 원본 스크립트" not in prompt


class TestMakeRegenerationRecord:
    def test_record_shape(self):
        rec = regeneration.make_regeneration_record("v_old", "v_new", reason="test")
        assert rec["original_video_id"] == "v_old"
        assert rec["new_video_id"] == "v_new"
        assert rec["reason"] == "test"
        assert "created_at" in rec
