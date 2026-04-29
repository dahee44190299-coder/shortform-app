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
    """API 키 없을 때, 사용자에게 수동 적용 방법 안내.

    쿠팡 파트너스 API는 '최종 승인 회원'만 받을 수 있음 (2024-2026 정책).
    초기 매출 0원 사용자는 API 없이 시작해야 하므로, 수동 subId가 핵심 흐름.
    """
    return (
        f"### 🎯 이 영상의 추적 ID\n"
        f"```\n{sub_id}\n```\n\n"
        f"**🔄 쿠팡 파트너스 사이트에서 단축 링크 만드는 법** (API 승인 전 단계):\n\n"
        f"1. https://partners.coupang.com 로그인\n"
        f"2. **링크 생성기** 메뉴 → 상품 URL 입력\n"
        f"3. **subId(서브 ID) 입력란**에 위 ID 그대로 붙여넣기:\n"
        f"   ```\n   {sub_id}\n   ```\n"
        f"4. **'단축 URL 생성'** 클릭 → `link.coupang.com/a/XXXXX` 받음\n"
        f"5. 그 단축 URL을 **영상 설명란**에 붙여넣기\n\n"
        f"---\n\n"
        f"**📊 7일 후 매출 확인하는 법**:\n\n"
        f"- 쿠팡 파트너스 → **수익 리포트** → 'subId별 보기'\n"
        f"- `{sub_id}` 검색 → 클릭/매출 숫자 확인\n"
        f"- 본 앱 STEP 4 추적 대시보드에 그 숫자 입력 → 케이스 스터디 자동 생성\n\n"
        f"💡 **CSV 업로드 가능**: 파트너스 → 리포트 → CSV 다운로드 → 본 앱 대시보드에 업로드 시 "
        f"subId 자동 매칭됩니다."
    )


def parse_partners_csv(file_content: bytes) -> list:
    """쿠팡 파트너스 매출 리포트 CSV → subId별 매출 dict.

    예상 CSV 컬럼 (쿠팡 표준):
      - subId / 서브ID / sub_id
      - 클릭수 / 클릭 / clicks
      - 수수료 / 매출 / commission

    Returns: [{"sub_id": str, "clicks": int, "revenue_krw": int}, ...]
    """
    import csv
    import io

    # utf-8-sig (BOM) → utf-8 → cp949 순서로 시도
    text = None
    for enc in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            text = file_content.decode(enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    if text is None:
        return []

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return []

    # 컬럼명 정규화 (한국어/영어 모두 지원)
    sub_keys = {"subId", "subid", "서브ID", "서브 ID", "sub_id", "SubId"}
    click_keys = {"클릭수", "클릭", "clicks", "Clicks"}
    rev_keys = {"수수료", "매출", "수수료(원)", "commission", "Commission", "Revenue"}

    def _find_col(fieldnames, candidates):
        for name in fieldnames:
            if name and name.strip() in candidates:
                return name
        # 부분 매칭
        for name in fieldnames:
            if not name:
                continue
            for cand in candidates:
                if cand.lower() in name.lower():
                    return name
        return None

    sub_col = _find_col(reader.fieldnames, sub_keys)
    click_col = _find_col(reader.fieldnames, click_keys)
    rev_col = _find_col(reader.fieldnames, rev_keys)

    if not sub_col:
        return []

    results = []
    for row in reader:
        sid = (row.get(sub_col) or "").strip()
        if not sid:
            continue
        clicks = 0
        revenue = 0
        if click_col:
            try:
                clicks = int(str(row.get(click_col, "0")).replace(",", "") or "0")
            except (ValueError, TypeError):
                pass
        if rev_col:
            try:
                rev_raw = str(row.get(rev_col, "0")).replace(",", "").replace("원", "").strip()
                revenue = int(float(rev_raw or "0"))
            except (ValueError, TypeError):
                pass
        results.append({
            "sub_id": sid,
            "clicks": clicks,
            "revenue_krw": revenue,
        })
    return results


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
