"""In-product PMF 검증 모듈.

Phase 0 스킵 결정의 직접 보완 — 도구 안에서 결제 의향과 NPS 측정.

저장: shortform_projects/_metrics/pmf_survey.jsonl
주기: 영상 5개 누적마다 1회 노출 (사용자 피로도 관리)
"""
import json
import os
from datetime import datetime, timezone


SURVEY_DIR = os.path.join("shortform_projects", "_metrics")
SURVEY_PATH = os.path.join(SURVEY_DIR, "pmf_survey.jsonl")
TRIGGER_EVERY_N_VIDEOS = 5


def should_show_survey(user_id: str, total_videos_made: int) -> bool:
    """이 사용자에게 지금 설문을 노출할지 결정.

    조건:
      - 영상 5개 이상 만들었을 때
      - 직전 응답에서 5개 이상 추가로 생성됐을 때
    """
    if total_videos_made < TRIGGER_EVERY_N_VIDEOS:
        return False
    last = _last_survey(user_id)
    if not last:
        return True
    return total_videos_made - int(last.get("videos_at_response", 0)) >= TRIGGER_EVERY_N_VIDEOS


def record_response(user_id: str, nps: int, would_pay: bool,
                     payment_amount_krw: int = 0,
                     reason: str = "",
                     videos_at_response: int = 0,
                     revenue_at_response: int = 0) -> bool:
    """설문 응답 1건 저장."""
    try:
        os.makedirs(SURVEY_DIR, exist_ok=True)
        rec = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id or "anonymous",
            "nps": int(nps),
            "would_pay": bool(would_pay),
            "payment_amount_krw": int(payment_amount_krw or 0),
            "reason": (reason or "")[:500],
            "videos_at_response": int(videos_at_response or 0),
            "revenue_at_response": int(revenue_at_response or 0),
        }
        with open(SURVEY_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def _last_survey(user_id: str):
    if not os.path.exists(SURVEY_PATH):
        return None
    last = None
    with open(SURVEY_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("user_id") == user_id:
                last = rec
    return last


def aggregate_nps_and_payment_intent() -> dict:
    """전체 응답 집계 — Go/No-Go 결정 데이터.

    Returns:
        {
            "n": int,
            "nps_score": float,             # NPS 표준 계산
            "promoters_pct": float,         # 9-10점 비율
            "detractors_pct": float,        # 0-6점 비율
            "would_pay_pct": float,         # 결제 의향 %
            "avg_payment_amount_krw": float,
            "go_no_go": "GO" | "NO_GO" | "NEED_MORE_DATA",
        }
    """
    if not os.path.exists(SURVEY_PATH):
        return _empty_result()
    recs = []
    with open(SURVEY_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    n = len(recs)
    if n == 0:
        return _empty_result()

    npss = [int(r.get("nps", 0)) for r in recs]
    promoters = sum(1 for s in npss if s >= 9)
    detractors = sum(1 for s in npss if s <= 6)
    nps_score = round(100 * (promoters - detractors) / n, 1)
    would_pay = sum(1 for r in recs if r.get("would_pay")) / n * 100
    pay_amounts = [int(r.get("payment_amount_krw", 0) or 0)
                   for r in recs if r.get("would_pay")]
    avg_pay = round(sum(pay_amounts) / len(pay_amounts), 0) if pay_amounts else 0

    # Go/No-Go (IMPROVEMENT_PLAN 게이트)
    if n < 10:
        decision = "NEED_MORE_DATA"
    elif would_pay >= 30 and (promoters / n * 100) >= 30:
        decision = "GO"
    else:
        decision = "NO_GO"

    return {
        "n": n,
        "nps_score": nps_score,
        "promoters_pct": round(promoters / n * 100, 1),
        "detractors_pct": round(detractors / n * 100, 1),
        "would_pay_pct": round(would_pay, 1),
        "avg_payment_amount_krw": avg_pay,
        "go_no_go": decision,
    }


def _empty_result() -> dict:
    return {
        "n": 0, "nps_score": 0, "promoters_pct": 0, "detractors_pct": 0,
        "would_pay_pct": 0, "avg_payment_amount_krw": 0,
        "go_no_go": "NEED_MORE_DATA",
    }
