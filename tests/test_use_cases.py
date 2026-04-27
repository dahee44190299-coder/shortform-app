"""use_cases.py 단위 테스트 — Phase 3 TAM 확장."""
import use_cases


class TestUseCaseRegistry:
    def test_4_use_cases_defined(self):
        ids = set(use_cases.USE_CASES.keys())
        assert ids == {
            "coupang_affiliate",
            "general_affiliate",
            "youtube_review",
            "personal_vlog",
        }

    def test_each_use_case_has_required_fields(self):
        required = {"label", "desc", "structure", "hook_style", "cta_style",
                    "performance_metrics", "primary_metric",
                    "tracking_required", "judge_weights"}
        for uid, prof in use_cases.USE_CASES.items():
            missing = required - set(prof.keys())
            assert not missing, f"{uid} missing: {missing}"

    def test_judge_weights_sum_to_1(self):
        for uid, prof in use_cases.USE_CASES.items():
            total = sum(prof["judge_weights"].values())
            assert abs(total - 1.0) < 0.01, f"{uid} weights = {total}"

    def test_get_unknown_returns_default(self):
        uc = use_cases.get_use_case("nonexistent_xyz")
        assert uc["label"] == use_cases.USE_CASES["coupang_affiliate"]["label"]


class TestListUseCases:
    def test_returns_id_label_desc_tuples(self):
        items = use_cases.list_use_cases()
        assert len(items) == 4
        for uid, label, desc in items:
            assert isinstance(uid, str)
            assert isinstance(label, str)
            assert isinstance(desc, str)


class TestFormatUseCaseHint:
    def test_includes_structure_and_hook_style(self):
        h = use_cases.format_use_case_hint("youtube_review")
        assert "리뷰" in h or "구독" in h or "Hook" in h
        assert "Use Case" in h


class TestWeightedJudgeScore:
    def test_perfect_scores_give_100(self):
        scores = {k: {"score": 20} for k in
                  ("hook_impact", "category_fit", "length_fit",
                   "cta_clarity", "conversion_power")}
        result = use_cases.weighted_judge_score(scores, "coupang_affiliate")
        assert result == 100.0

    def test_zero_scores_give_0(self):
        scores = {k: {"score": 0} for k in
                  ("hook_impact", "category_fit", "length_fit",
                   "cta_clarity", "conversion_power")}
        result = use_cases.weighted_judge_score(scores, "coupang_affiliate")
        assert result == 0.0

    def test_personal_vlog_weights_hook_heavily(self):
        # vlog는 hook_impact 가중치 0.40
        # hook만 만점, 나머지 0 → 20*5*0.40 = 40
        scores = {
            "hook_impact":      {"score": 20},
            "category_fit":     {"score": 0},
            "length_fit":       {"score": 0},
            "cta_clarity":      {"score": 0},
            "conversion_power": {"score": 0},
        }
        vlog_score = use_cases.weighted_judge_score(scores, "personal_vlog")
        assert vlog_score == 40.0
        # 같은 점수라도 coupang은 hook 가중치 0.20 → 20*5*0.20 = 20
        coupang_score = use_cases.weighted_judge_score(scores, "coupang_affiliate")
        assert coupang_score == 20.0


class TestPrimaryMetricLabel:
    def test_returns_korean_labels(self):
        assert use_cases.primary_metric_label("coupang_affiliate") == "매출 (원)"
        assert use_cases.primary_metric_label("youtube_review") == "조회수"
        assert use_cases.primary_metric_label("personal_vlog") == "조회수"

    def test_unknown_use_case_default(self):
        assert use_cases.primary_metric_label("xyz_nonexistent") == "매출 (원)"
