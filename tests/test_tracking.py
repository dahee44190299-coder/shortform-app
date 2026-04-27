"""tracking.py 단위 테스트 — Phase 1-B 추적 링크 회귀 방지."""
import re
from datetime import datetime, timezone

import tracking


class TestGenerateVideoSubid:
    def test_format_matches_spec(self):
        sub = tracking.generate_video_subid()
        # vid_YYYYMMDD_<6 hex>
        assert re.fullmatch(r"vid_\d{8}_[0-9a-f]{6}", sub), sub

    def test_uniqueness(self):
        ids = {tracking.generate_video_subid() for _ in range(100)}
        # 100회 생성 시 충돌 확률은 무시 가능 (16^6 = 16M 공간)
        assert len(ids) == 100

    def test_custom_prefix(self):
        sub = tracking.generate_video_subid(prefix="ab")
        assert sub.startswith("ab_")

    def test_date_is_today_utc(self):
        sub = tracking.generate_video_subid()
        date_part = sub.split("_")[1]
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        assert date_part == today


class TestCreatePartnersDeeplink:
    def test_missing_keys_returns_error(self):
        r = tracking.create_partners_deeplink("https://coupang.com/x", "vid_x", "", "")
        assert r["ok"] is False
        assert "키" in r["error"]

    def test_empty_url_returns_error(self):
        r = tracking.create_partners_deeplink("", "vid_x", "ak", "sk")
        assert r["ok"] is False
        assert "URL" in r["error"]


class TestMakeTrackingRecord:
    def test_minimal_record_shape(self):
        rec = tracking.make_tracking_record(
            video_id="vid_test", project_id="prj_x",
            coupang_url="https://coupang.com/p/123",
        )
        # 필수 필드
        assert rec["video_id"] == "vid_test"
        assert rec["project_id"] == "prj_x"
        assert rec["original_url"] == "https://coupang.com/p/123"
        assert rec["manual_clicks"] == 0
        assert rec["manual_revenue_krw"] == 0
        assert rec["uploaded_to"] == []
        assert "created_at" in rec

    def test_with_deeplink_result(self):
        deeplink = {
            "subId": "vid_x",
            "shortenUrl": "https://link.coupang.com/a/abc",
            "landingUrl": "https://coupang.com/full/url",
        }
        rec = tracking.make_tracking_record(
            video_id="v1", project_id="p1",
            coupang_url="https://coupang.com/x",
            deeplink_result=deeplink,
            template="문제해결형", title="배수구 냄새 끝",
        )
        assert rec["sub_id"] == "vid_x"
        assert rec["shorten_url"] == "https://link.coupang.com/a/abc"
        assert rec["landing_url"] == "https://coupang.com/full/url"
        assert rec["template"] == "문제해결형"
        assert rec["title"] == "배수구 냄새 끝"


class TestManualSubidInstructions:
    def test_contains_subid(self):
        msg = tracking.manual_subid_instructions("vid_20260424_abc123")
        assert "vid_20260424_abc123" in msg
        assert "쿠팡 파트너스" in msg
