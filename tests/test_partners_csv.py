"""쿠팡 파트너스 CSV 파서 단위 테스트."""
import tracking


class TestParsePartnersCsv:
    def test_empty_returns_empty(self):
        assert tracking.parse_partners_csv(b"") == []

    def test_korean_columns(self):
        csv = "subId,클릭수,수수료\nvid_001,15,3500\nvid_002,8,1800\n"
        result = tracking.parse_partners_csv(csv.encode("utf-8-sig"))
        assert len(result) == 2
        assert result[0]["sub_id"] == "vid_001"
        assert result[0]["clicks"] == 15
        assert result[0]["revenue_krw"] == 3500

    def test_english_columns(self):
        csv = "SubId,Clicks,Commission\nvid_x,10,5000\n"
        result = tracking.parse_partners_csv(csv.encode("utf-8-sig"))
        assert len(result) == 1
        assert result[0]["clicks"] == 10
        assert result[0]["revenue_krw"] == 5000

    def test_subid_only_no_metrics(self):
        csv = "subId\nvid_a\nvid_b\n"
        result = tracking.parse_partners_csv(csv.encode("utf-8-sig"))
        assert len(result) == 2
        assert all(r["clicks"] == 0 and r["revenue_krw"] == 0 for r in result)

    def test_skips_empty_subid(self):
        csv = "subId,클릭수\nvid_a,5\n,10\n   ,20\nvid_b,3\n"
        result = tracking.parse_partners_csv(csv.encode("utf-8-sig"))
        assert len(result) == 2
        assert {r["sub_id"] for r in result} == {"vid_a", "vid_b"}

    def test_revenue_with_commas(self):
        csv = "subId,수수료\nvid_a,\"15,000\"\nvid_b,\"1,234,567\"\n"
        result = tracking.parse_partners_csv(csv.encode("utf-8-sig"))
        assert result[0]["revenue_krw"] == 15000
        assert result[1]["revenue_krw"] == 1234567

    def test_no_subid_column_returns_empty(self):
        csv = "이름,수치\nABC,100\n"
        result = tracking.parse_partners_csv(csv.encode("utf-8-sig"))
        assert result == []

    def test_partial_column_match(self):
        # "서브 ID" 같은 변형도 인식
        csv = "서브 ID,클릭\nvid_x,5\n"
        result = tracking.parse_partners_csv(csv.encode("utf-8-sig"))
        assert len(result) == 1
        assert result[0]["sub_id"] == "vid_x"

    def test_invalid_numeric_values_default_to_zero(self):
        csv = "subId,클릭수,수수료\nvid_a,abc,xyz\n"
        result = tracking.parse_partners_csv(csv.encode("utf-8-sig"))
        assert result[0]["clicks"] == 0
        assert result[0]["revenue_krw"] == 0
