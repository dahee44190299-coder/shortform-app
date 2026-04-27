"""marketing_auto.py + pmf_survey.py 단위 테스트."""
import json

import pytest

import marketing_auto
import pmf_survey
import project_store


# ── marketing_auto ────────────────────────────────────────────────

@pytest.fixture
def isolated_store_marketing(tmp_path, monkeypatch):
    fake = tmp_path / "shortform_projects"
    fake.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(project_store, "PROJECTS_DIR", str(fake))
    return fake


class TestAggregateSalesStats:
    def test_no_data_returns_zeros(self, isolated_store_marketing):
        s = marketing_auto.aggregate_sales_stats(days=7)
        assert s["total_videos"] == 0
        assert s["total_revenue_krw"] == 0
        assert s["best_performer"] is None

    def test_with_data_aggregates(self, isolated_store_marketing):
        pid = project_store.create_project("p")
        project_store.add_tracking_record(pid, {
            "video_id": "v1", "title": "t1",
            "manual_clicks": 10, "manual_revenue_krw": 5000,
        })
        project_store.add_tracking_record(pid, {
            "video_id": "v2", "title": "t2",
            "manual_clicks": 20, "manual_revenue_krw": 15000,
        })
        s = marketing_auto.aggregate_sales_stats(days=365)
        assert s["total_videos"] == 2
        assert s["total_clicks"] == 30
        assert s["total_revenue_krw"] == 20000
        assert s["best_performer"]["revenue"] == 15000


class TestGenerateCaseStudy:
    def test_contains_essentials(self):
        rec = {
            "title": "테스트 영상", "project_name": "프로젝트A",
            "sub_id": "vid_xxx", "manual_clicks": 50,
            "manual_revenue_krw": 25000, "shorten_url": "https://link.coupang/x",
            "created_at": "2026-04-27T00:00:00",
        }
        md = marketing_auto.generate_case_study(rec)
        assert "테스트 영상" in md
        assert "25,000" in md
        assert "vid_xxx" in md
        assert "shortform-app" in md  # cross-promotion


class TestGenerateSocialPost:
    def test_with_revenue_includes_amount(self):
        post = marketing_auto.generate_social_post({
            "period_days": 7, "total_videos": 5,
            "total_clicks": 100, "total_revenue_krw": 50000,
        })
        assert "50,000" in post
        assert "#쿠팡파트너스" in post

    def test_zero_revenue_uses_build_in_public(self):
        post = marketing_auto.generate_social_post({
            "period_days": 7, "total_videos": 3,
            "total_clicks": 5, "total_revenue_krw": 0,
        })
        assert "BuildInPublic" in post


class TestExportCaseStudies:
    def test_only_revenue_records_exported(self, isolated_store_marketing):
        pid = project_store.create_project("p")
        project_store.add_tracking_record(pid, {
            "video_id": "v1", "title": "no revenue",
            "manual_clicks": 0, "manual_revenue_krw": 0,
            "created_at": "2026-04-27",
        })
        project_store.add_tracking_record(pid, {
            "video_id": "v2", "title": "with revenue",
            "manual_clicks": 10, "manual_revenue_krw": 5000,
            "sub_id": "vid_b",
            "created_at": "2026-04-27",
        })
        paths = marketing_auto.export_case_studies(min_revenue=1)
        assert len(paths) == 1


# ── pmf_survey ────────────────────────────────────────────────

@pytest.fixture
def isolated_survey(tmp_path, monkeypatch):
    fake_dir = tmp_path / "shortform_projects" / "_metrics"
    monkeypatch.setattr(pmf_survey, "SURVEY_DIR", str(fake_dir))
    monkeypatch.setattr(pmf_survey, "SURVEY_PATH",
                        str(fake_dir / "pmf_survey.jsonl"))
    yield fake_dir


class TestShouldShowSurvey:
    def test_too_few_videos(self, isolated_survey):
        assert pmf_survey.should_show_survey("u1", 3) is False

    def test_first_time_after_threshold(self, isolated_survey):
        assert pmf_survey.should_show_survey("u1", 5) is True

    def test_after_response_waits_for_more(self, isolated_survey):
        pmf_survey.record_response("u1", nps=8, would_pay=True,
                                    videos_at_response=5)
        assert pmf_survey.should_show_survey("u1", 6) is False
        assert pmf_survey.should_show_survey("u1", 10) is True


class TestAggregateNps:
    def test_empty(self, isolated_survey):
        a = pmf_survey.aggregate_nps_and_payment_intent()
        assert a["n"] == 0
        assert a["go_no_go"] == "NEED_MORE_DATA"

    def test_need_more_data_under_10(self, isolated_survey):
        for i in range(5):
            pmf_survey.record_response(f"u{i}", nps=10, would_pay=True,
                                        payment_amount_krw=20000)
        a = pmf_survey.aggregate_nps_and_payment_intent()
        assert a["n"] == 5
        assert a["go_no_go"] == "NEED_MORE_DATA"

    def test_go_decision(self, isolated_survey):
        # 10명 중 4명 promoter (9-10점) + 모두 결제 의향
        for i in range(10):
            pmf_survey.record_response(f"u{i}", nps=9 if i < 4 else 5,
                                        would_pay=True, payment_amount_krw=20000)
        a = pmf_survey.aggregate_nps_and_payment_intent()
        assert a["promoters_pct"] == 40.0
        assert a["would_pay_pct"] == 100.0
        assert a["go_no_go"] == "GO"

    def test_no_go_decision(self, isolated_survey):
        # 10명 중 결제 의향 1명 (10%) → NO_GO
        for i in range(10):
            pmf_survey.record_response(f"u{i}", nps=5,
                                        would_pay=(i == 0),
                                        payment_amount_krw=10000)
        a = pmf_survey.aggregate_nps_and_payment_intent()
        assert a["go_no_go"] == "NO_GO"

    def test_nps_calculation(self, isolated_survey):
        # 10명: promoter 5명(9-10), detractor 3명(0-6), passive 2명(7-8)
        scores = [10, 10, 9, 9, 9, 8, 7, 5, 3, 0]
        for i, s in enumerate(scores):
            pmf_survey.record_response(f"u{i}", nps=s, would_pay=False)
        a = pmf_survey.aggregate_nps_and_payment_intent()
        # NPS = (promoters - detractors) / n * 100 = (5 - 3) / 10 * 100 = 20
        assert a["nps_score"] == 20.0


class TestRecordResponse:
    def test_writes_jsonl(self, isolated_survey):
        ok = pmf_survey.record_response("u1", nps=8, would_pay=True,
                                         payment_amount_krw=15000,
                                         reason="진짜 편함",
                                         videos_at_response=10,
                                         revenue_at_response=50000)
        assert ok is True
        path = isolated_survey / "pmf_survey.jsonl"
        rec = json.loads(path.read_text(encoding="utf-8").strip())
        assert rec["nps"] == 8
        assert rec["would_pay"] is True
        assert rec["payment_amount_krw"] == 15000
        assert rec["videos_at_response"] == 10
