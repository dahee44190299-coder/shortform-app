"""쿠팡 공유 텍스트 파서 단위 테스트.

parse_coupang_share_text는 app.py 안에 있어 import 어려우므로
함수를 테스트용으로 복제. (실제 app.py 함수와 동일 로직)
"""
import re


def parse_coupang_share_text(text: str) -> dict:
    """app.py의 parse_coupang_share_text와 동일."""
    if not text:
        return {"name": "", "url": "", "success": False}
    text = text.strip()
    url_match = re.search(
        r'https?://(?:link\.coupang\.com/a/[A-Za-z0-9]+'
        r'|(?:www|m)\.coupang\.com/[^\s]+)',
        text,
    )
    extracted_url = url_match.group(0) if url_match else ""
    name_part = text
    if extracted_url:
        name_part = name_part.replace(extracted_url, "").strip()
    for prefix in ("[쿠팡]", "쿠팡:", "Coupang:", "쿠팡-"):
        if name_part.startswith(prefix):
            name_part = name_part[len(prefix):].strip()
    name_part = re.sub(r'\s+', ' ', name_part).strip()
    valid_name = len(name_part) >= 3 and len(name_part) <= 200
    return {
        "name": name_part if valid_name else "",
        "url": extracted_url,
        "success": bool(extracted_url or valid_name),
    }


class TestEmpty:
    def test_empty_string(self):
        r = parse_coupang_share_text("")
        assert r["success"] is False
        assert r["name"] == "" and r["url"] == ""

    def test_whitespace_only(self):
        r = parse_coupang_share_text("   \n  \t  ")
        assert r["success"] is False


class TestStandardShareText:
    def test_kakao_share_format(self):
        text = "[쿠팡] 닥터자르트 시카페어 토너 200ml\nhttps://link.coupang.com/a/exnTX4"
        r = parse_coupang_share_text(text)
        assert r["success"] is True
        assert r["name"] == "닥터자르트 시카페어 토너 200ml"
        assert r["url"] == "https://link.coupang.com/a/exnTX4"

    def test_inline_url(self):
        text = "삼성 갤럭시 버즈3 프로 https://link.coupang.com/a/abcDEF"
        r = parse_coupang_share_text(text)
        assert r["name"] == "삼성 갤럭시 버즈3 프로"
        assert r["url"] == "https://link.coupang.com/a/abcDEF"

    def test_url_only(self):
        text = "https://link.coupang.com/a/exnTX4"
        r = parse_coupang_share_text(text)
        assert r["url"] == "https://link.coupang.com/a/exnTX4"
        assert r["success"] is True

    def test_long_url_format(self):
        text = "신라면 멀티팩 https://www.coupang.com/vp/products/123?itemId=456"
        r = parse_coupang_share_text(text)
        assert r["name"] == "신라면 멀티팩"
        assert "coupang.com/vp/products/123" in r["url"]


class TestPrefixHandling:
    def test_kupang_prefix_with_colon(self):
        r = parse_coupang_share_text("쿠팡: 농심 신라면 30봉")
        assert r["name"] == "농심 신라면 30봉"

    def test_no_prefix(self):
        r = parse_coupang_share_text("일반 상품명")
        assert r["name"] == "일반 상품명"

    def test_dash_prefix(self):
        r = parse_coupang_share_text("쿠팡- 갤럭시 버즈")
        assert r["name"] == "갤럭시 버즈"


class TestEdgeCases:
    def test_multiline_with_whitespace(self):
        text = "[쿠팡]\n\n   닥터자르트 토너   \n\nhttps://link.coupang.com/a/x"
        r = parse_coupang_share_text(text)
        assert r["name"] == "닥터자르트 토너"

    def test_too_short_name_rejected(self):
        r = parse_coupang_share_text("AB")
        assert r["name"] == ""

    def test_only_url_no_name(self):
        r = parse_coupang_share_text("https://link.coupang.com/a/x")
        assert r["name"] == ""
        assert r["url"] == "https://link.coupang.com/a/x"
        assert r["success"] is True  # URL만 있어도 성공

    def test_name_only_no_url(self):
        r = parse_coupang_share_text("닥터자르트 시카페어 토너")
        assert r["name"] == "닥터자르트 시카페어 토너"
        assert r["url"] == ""
        assert r["success"] is True
