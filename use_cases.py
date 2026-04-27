"""Use Case 추상화 (Phase 3 — TAM 확장).

전략 (2026-04-27):
  쿠팡 파트너스 단일 → 4개 use case로 확장.
  핵심 가치 ("성과 추적 + LLM judge + 자동 재생성")은 모두 동일.
  use case별로 다른 것: 영상 구조, Hook 패턴, 성과 지표, CTA 형식.

Use Cases:
  1. coupang_affiliate (현재 core) — 쿠팡 파트너스 매출 추적
  2. general_affiliate — Amazon/Shopee/배달의민족 등 다른 affiliate
  3. youtube_review — 일반 유튜브 리뷰/언박싱 (구독·시청 추적)
  4. personal_vlog — 개인 브이로그/숏폼 (조회·좋아요 추적)

설계:
  - 각 use case = profile dict (name/desc/structure/hook_style/cta_style/performance_metric)
  - script_judge가 use case 인자 받아 평가 기준 차등 적용
  - tracking.py가 metric_type별로 record (revenue/views/likes/subs)
  - UI는 use case 선택 후 그에 맞는 카테고리/템플릿만 노출
"""

USE_CASES = {
    "coupang_affiliate": {
        "label": "🛒 쿠팡 파트너스",
        "desc": "쿠팡 상품 영상 + 추적 링크 + 매출 회수",
        "structure": "Hook → 문제/욕구 → 해결책(상품) → 가격/혜택 → CTA(쿠팡 링크)",
        "hook_style": "구체적 가격/수치 + 의문문 (예: '이 가격에 이 스펙?')",
        "cta_style": "설명란 쿠팡 링크 클릭 유도, '지금 할인 중' 류 긴급성",
        "performance_metrics": ["clicks", "revenue_krw", "ctr"],
        "primary_metric": "revenue_krw",
        "tracking_required": True,  # subId 자동 부착 필수
        "default_categories": ["digital", "beauty", "food", "household",
                               "fashion", "baby_kids", "pet"],
        "judge_weights": {
            "hook_impact": 0.20,
            "category_fit": 0.15,
            "specificity": 0.20,  # 구체성 — 쿠팡은 가격/스펙이 결정
            "anti_cliche": 0.20,
            "conversion_power": 0.25,
            # legacy 호환:
            "length_fit": 0.15,
            "cta_clarity": 0.20,
        },
    },
    "general_affiliate": {
        "label": "🌍 기타 부업/제휴",
        "desc": "Amazon, Shopee, 배달의민족, 토스 추천 등 일반 affiliate",
        "structure": "Hook → 문제/공감 → 솔루션(서비스) → 가입/할인 혜택 → CTA",
        "hook_style": "월 X만원 같은 수치, '이거 모르면 손해' 류",
        "cta_style": "추천 링크/코드, 첫 가입 보너스 강조",
        "performance_metrics": ["clicks", "signups", "revenue_krw"],
        "primary_metric": "revenue_krw",
        "tracking_required": True,
        "default_categories": ["digital", "food", "fashion", "general"],
        "judge_weights": {
            "hook_impact": 0.20,
            "category_fit": 0.15,
            "length_fit": 0.15,
            "cta_clarity": 0.25,
            "conversion_power": 0.25,
        },
    },
    "youtube_review": {
        "label": "📹 유튜브 리뷰/언박싱",
        "desc": "제품 리뷰/언박싱 영상 (광고 수익 + 구독자 확보)",
        "structure": "Hook(궁금증) → 언박싱/사용 → 장단점 → 평가 → 구독 CTA",
        "hook_style": "리뷰 결과 스포일러 또는 강한 의견 (예: '이거 사면 후회합니다')",
        "cta_style": "구독·좋아요·알림 설정, '다음 영상 더 솔직한 리뷰'",
        "performance_metrics": ["views", "likes", "subscribers_gained", "watch_time"],
        "primary_metric": "views",
        "tracking_required": False,  # YouTube Analytics 수동 입력
        "default_categories": ["digital", "beauty", "food", "household",
                               "general"],
        "judge_weights": {
            "hook_impact": 0.30,  # 시청률 = Hook이 거의 전부
            "category_fit": 0.15,
            "length_fit": 0.15,
            "cta_clarity": 0.15,
            "conversion_power": 0.25,  # 구독 전환력
        },
    },
    "personal_vlog": {
        "label": "🎬 개인 브이로그/숏폼",
        "desc": "일상 브이로그, 챌린지, 개인 콘텐츠 (조회수·좋아요 중심)",
        "structure": "Hook(상황) → 전개 → 클라이맥스/반전 → 마무리 (광고 X)",
        "hook_style": "공감/호기심 위주, 친근한 반말 (예: '오늘 진짜 웃겼던 일')",
        "cta_style": "좋아요·팔로우 자연스럽게, 다음 콘텐츠 예고",
        "performance_metrics": ["views", "likes", "shares", "saves"],
        "primary_metric": "views",
        "tracking_required": False,
        "default_categories": ["general"],  # 카테고리 가이드 의미 약함
        "judge_weights": {
            "hook_impact": 0.40,  # 알고리즘 = Hook이 전부
            "category_fit": 0.05,  # 카테고리 의미 약함
            "length_fit": 0.20,  # 짧을수록 retention
            "cta_clarity": 0.10,  # CTA 강요하면 오히려 마이너스
            "conversion_power": 0.25,  # 좋아요/저장 유발력
        },
    },
}


def get_use_case(use_case_id: str) -> dict:
    """알 수 없으면 default(coupang_affiliate)."""
    return USE_CASES.get(use_case_id, USE_CASES["coupang_affiliate"])


def list_use_cases() -> list:
    """UI 선택용 [(id, label, desc), ...]."""
    return [(uid, u["label"], u["desc"]) for uid, u in USE_CASES.items()]


def format_use_case_hint(use_case_id: str) -> str:
    """LLM 프롬프트에 주입할 use case 가이드 블록.

    카테고리 가이드와 함께 사용 (use case + category 이중 가이드).
    """
    uc = get_use_case(use_case_id)
    return (
        f"[Use Case: {uc['label']}]\n"
        f"- 영상 구조: {uc['structure']}\n"
        f"- Hook 스타일: {uc['hook_style']}\n"
        f"- CTA 스타일: {uc['cta_style']}\n"
        f"- 핵심 성과 지표: {uc['primary_metric']}\n"
    )


def weighted_judge_score(scores: dict, use_case_id: str) -> float:
    """5차원 점수에 use case별 가중치 적용 → 단일 점수.

    Args:
        scores: {hook_impact: {score: int}, category_fit: {...}, ...}
        use_case_id: use case id

    Returns:
        가중 평균 점수 (0-100)
    """
    uc = get_use_case(use_case_id)
    weights = uc.get("judge_weights", {})
    if not weights:
        # 가중치 없으면 단순 합 / 5 * 100/20 = total
        total_pts = sum(int(scores.get(k, {}).get("score", 0))
                        for k in ("hook_impact", "category_fit", "length_fit",
                                  "cta_clarity", "conversion_power"))
        return float(total_pts)
    # 점수가 있는 차원만 필터 + 가중치 정규화 (sum 1.0)
    present_weights = {k: w for k, w in weights.items()
                        if k in scores and scores[k].get("score")}
    if not present_weights:
        return 0.0
    total_w = sum(present_weights.values())
    if total_w == 0:
        return 0.0
    norm_weights = {k: w / total_w for k, w in present_weights.items()}
    # 가중치는 합이 1.0, 각 점수는 0-20이므로 *5 = 0-100 환산
    weighted = 0.0
    for k, w in norm_weights.items():
        s = int(scores.get(k, {}).get("score", 0))
        weighted += s * 5 * w
    return round(weighted, 1)


def primary_metric_label(use_case_id: str) -> str:
    """UI에 표시할 성과 지표 라벨."""
    uc = get_use_case(use_case_id)
    pm = uc.get("primary_metric", "revenue_krw")
    labels = {
        "revenue_krw": "매출 (원)",
        "views": "조회수",
        "likes": "좋아요",
        "clicks": "클릭",
        "signups": "가입자",
        "subscribers_gained": "신규 구독",
    }
    return labels.get(pm) or pm
