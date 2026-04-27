"""쿠팡 파트너스 추적 링크 관리 모듈 (Phase 1-B).

핵심 기능:
- 영상별 고유 subId 생성 (vid_YYYYMMDD_xxxxx)
- 쿠팡 Partners Open API로 deeplink 자동 생성 (키 있을 때)
- 키 없을 때: subId만 생성 → 사용자가 파트너스 대시보드에서 수동 적용
- 영상↔subId↔deeplink 매핑을 project_store에 저장하여 사후 매출 귀속 가능

Why 해자:
영상마다 unique subId 부착 → 어떤 영상이 매출 냈는지 추적 가능.
다른 도구(Mirr/CapCut/Invideo)는 영상만 만들고 끝. 우리는 매출까지 본다.
"""
import hmac
import hashlib
import json
import secrets
import requests
from datetime import datetime, timezone


COUPANG_API_DOMAIN = "https://api-gateway.coupang.com"
DEEPLINK_PATH = "/v2/providers/affiliate_open_api/apis/openapi/v1/deeplink"


def generate_video_subid(prefix: str = "vid") -> str:
    """영상별 고유 subId 생성.
    형식: vid_YYYYMMDD_<6자리 랜덤>  (예: vid_20260424_a3f9c1)
    쿠팡 subId 제한(영문/숫자/언더스코어, 100자 이내) 준수.
    """
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    rand = secrets.token_hex(3)
    return f"{prefix}_{today}_{rand}"


def _coupang_hmac_signature(method: str, url_path: str, query: str,
                             access_key: str, secret_key: str) -> str:
    """쿠팡 Partners Open API HMAC-SHA256 서명 생성."""
    datetime_gmt = datetime.now(timezone.utc).strftime("%y%m%dT%H%M%SZ")
    message = datetime_gmt + method + url_path + query
    signature = hmac.new(
        bytes(secret_key, "utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return (
        f"CEA algorithm=HmacSHA256, access-key={access_key}, "
        f"signed-date={datetime_gmt}, signature={signature}"
    )


def create_partners_deeplink(coupang_url: str, sub_id: str,
                              access_key: str, secret_key: str,
                              timeout: int = 10) -> dict:
    """쿠팡 Partners API로 단축 deeplink 생성.

    Returns:
      {"ok": True, "shortenUrl": "https://link.coupang.com/a/...",
       "landingUrl": "...", "originalUrl": coupang_url, "subId": sub_id}
      또는
      {"ok": False, "error": "..."}
    """
    if not access_key or not secret_key:
        return {"ok": False, "error": "API 키 미설정"}
    if not coupang_url:
        return {"ok": False, "error": "URL 비어있음"}

    payload = {"coupangUrls": [coupang_url], "subId": sub_id}
    auth = _coupang_hmac_signature("POST", DEEPLINK_PATH, "", access_key, secret_key)

    try:
        resp = requests.post(
            COUPANG_API_DOMAIN + DEEPLINK_PATH,
            headers={"Authorization": auth, "Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=timeout,
        )
        if resp.status_code != 200:
            return {"ok": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
        data = resp.json().get("data", [])
        if not data:
            return {"ok": False, "error": "응답 데이터 비어있음"}
        first = data[0]
        return {
            "ok": True,
            "shortenUrl": first.get("shortenUrl", ""),
            "landingUrl": first.get("landingUrl", ""),
            "originalUrl": first.get("originalUrl", coupang_url),
            "subId": sub_id,
        }
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:150]}"}


def manual_subid_instructions(sub_id: str) -> str:
    """API 키 없을 때, 사용자에게 수동 적용 방법 안내."""
    return (
        f"이 영상의 추적 ID: **`{sub_id}`**\n\n"
        "1. 쿠팡 파트너스 대시보드 → 도구 → 링크 생성기 진입\n"
        f"2. 상품 URL 입력 후 **subId 입력란에 `{sub_id}` 복사 붙여넣기**\n"
        "3. 생성된 링크를 영상 설명란에 사용\n\n"
        "→ 7일 후 파트너스 리포트에서 이 ID로 클릭/매출 확인 가능"
    )


def make_tracking_record(video_id: str, project_id: str, coupang_url: str = "",
                          deeplink_result: dict | None = None,
                          template: str = "", title: str = "",
                          use_case: str = "coupang_affiliate") -> dict:
    """추적 레코드 1건. project_store에 저장될 dict.

    Phase 3 일반화 (2026-04-27):
      - 매출 외 성과 지표 추가 (views/likes/subscribers_gained 등)
      - use_case 필드로 어떤 종류의 영상인지 표시
      - 비-affiliate use case (vlog 등)는 sub_id/shorten_url 비워둬도 됨
    """
    return {
        "video_id": video_id,
        "project_id": project_id,
        "use_case": use_case,
        "sub_id": (deeplink_result or {}).get("subId", ""),
        "shorten_url": (deeplink_result or {}).get("shortenUrl", ""),
        "landing_url": (deeplink_result or {}).get("landingUrl", ""),
        "original_url": coupang_url,
        "template": template,
        "title": title,
        "created_at": datetime.now(timezone.utc).isoformat(),
        # 성과 지표 — use case별로 사용자가 채울 필드:
        "manual_clicks": 0,
        "manual_revenue_krw": 0,        # affiliate
        "manual_views": 0,              # youtube_review, personal_vlog
        "manual_likes": 0,              # personal_vlog
        "manual_subscribers": 0,        # youtube_review
        "manual_signups": 0,            # general_affiliate
        "uploaded_to": [],              # ["youtube", "tiktok", ...]
    }


def primary_metric_value(record: dict) -> int:
    """레코드에서 use case별 주요 성과 지표 값 추출."""
    try:
        import use_cases
        uc = use_cases.get_use_case(record.get("use_case", "coupang_affiliate"))
        pm = uc.get("primary_metric", "revenue_krw")
    except Exception:
        pm = "revenue_krw"
    field_map = {
        "revenue_krw": "manual_revenue_krw",
        "views": "manual_views",
        "likes": "manual_likes",
        "clicks": "manual_clicks",
        "signups": "manual_signups",
        "subscribers_gained": "manual_subscribers",
    }
    field = field_map.get(pm, "manual_revenue_krw")
    return int(record.get(field, 0) or 0)
