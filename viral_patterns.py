"""한국 숏폼 viral 패턴 라이브러리.

조회수 100만+ 한국 영상 분석으로 도출한 12가지 검증된 패턴.
LLM이 무작위 + 의도적으로 골라 쓸 수 있게 명시적 예시 + 트리거 제공.

직전 사용자 피드백: "뭔가 대본이 획기적이었음 좋겠는데"
→ 단순한 친근한 톤은 부족. 시청자가 "어?" 하고 멈추는 패턴 필요.

각 패턴 = (id, label, when_to_use, structure_hint, opener_examples, full_example)
"""

VIRAL_PATTERNS = {
    "shocking_stat": {
        "label": "💥 충격 통계",
        "when": "수치/비율로 시청자가 '진짜?' 하게 만들 때",
        "hint": "구체적 % 또는 '몇 명 중 1명' 식 비율로 시작",
        "openers": [
            "한국인 70%가 모르는 이거.",
            "10명 중 9명이 잘못 쓰고 있어.",
            "이거 안 쓰면 1년에 30만원 손해야.",
        ],
        "example": (
            "한국인 90%가 이거 모르고 비싸게 사.\n"
            "쿠팡 검색하면 같은 제품 절반 가격이거든.\n"
            "내가 직접 비교한 표 만들어봤는데 진짜 미친 가격차야.\n"
            "{product} 기준으로 일반 매장 4만5천원, 쿠팡 2만3천원.\n"
            "심지어 로켓배송이라 내일 도착.\n"
            "링크 설명란에 두고 갈게."
        ),
    },
    "personal_failure": {
        "label": "💔 개인 실패→깨달음",
        "when": "본인 실수/손해 사연이 있을 때 (가장 강력)",
        "hint": "'5년 동안 이거 모르고 X만원 날렸어' 패턴",
        "openers": [
            "5년 동안 이거 모르고 200만원 날렸어.",
            "처음 샀을 때 진짜 후회했거든.",
            "이거 알기 전엔 매달 X만원 새고 있었어.",
        ],
        "example": (
            "3년 동안 비싼 거 사다가 진짜 화났어.\n"
            "{product} 만나기 전까지 매달 5만원씩 날린 셈이야.\n"
            "이거 한 번 사면 6개월 가는데\n"
            "예전에 쓰던 건 한 달도 안 됐거든.\n"
            "솔직히 더 일찍 알았으면 좋았을 거 같아.\n"
            "링크 두고 갈게. 후회하지 마."
        ),
    },
    "insider_secret": {
        "label": "🤫 내부자 비밀",
        "when": "업계/현직자 입장에서 말할 때",
        "hint": "'유튜버/대기업/판매자가 안 알려주는 진짜 이유'",
        "openers": [
            "쇼핑몰에서 안 알려주는 진실 알려줄게.",
            "유튜버들은 이거 절대 말 안 해.",
            "현직자만 아는 진짜 좋은 제품.",
        ],
        "example": (
            "업계에서 일하는 사람들은 다 이거 써.\n"
            "{product} 같은 거.\n"
            "왜 마케팅 안 하냐면, 단가 너무 낮아서 광고비 못 빼.\n"
            "그래서 입소문으로만 팔려.\n"
            "쿠팡에 검색하면 바로 나와.\n"
            "리뷰만 봐도 답 나옴."
        ),
    },
    "reverse_hook": {
        "label": "🔄 반전 후킹",
        "when": "처음에 부정 → 마지막에 반전",
        "hint": "'이거 사지 마... 라고 말하려 했는데' 패턴",
        "openers": [
            "이거 절대 사지 마.",
            "솔직히 추천 안 하려 했는데.",
            "처음엔 별로일 거라 생각했어.",
        ],
        "example": (
            "이거 사지 말라고 영상 만들 뻔했어.\n"
            "근데 한 달 써보니까 미쳤더라.\n"
            "{product} 솔직히 처음엔 의심했거든.\n"
            "근데 첫날부터 차이 느낌.\n"
            "지금은 못 끊음.\n"
            "쿠팡 링크 설명란."
        ),
    },
    "countdown": {
        "label": "📋 카운트다운 (3가지/5가지)",
        "when": "정보 정리형 (리스트 콘텐츠)",
        "hint": "'X가지 이유' '딱 3개만'",
        "openers": [
            "이거 사야 하는 진짜 이유 3가지.",
            "30초 안에 끝낼게. 5개만.",
            "딱 3개만 기억해.",
        ],
        "example": (
            "{product} 사야 하는 이유 딱 3개.\n"
            "1. 같은 가격 다른 제품 대비 용량 2배.\n"
            "2. 쿠팡 로켓배송으로 내일 도착.\n"
            "3. 별점 4.8에 리뷰 5천 개 넘음.\n"
            "끝. 진짜 이게 다야.\n"
            "링크 설명란."
        ),
    },
    "fear_loss": {
        "label": "⚠️ 공포 + 손해 회피",
        "when": "'안 사면 손해' 강조",
        "hint": "구체적 손실 금액/시간/기회",
        "openers": [
            "이거 모르면 매년 50만원 새요.",
            "지금 안 알아두면 후회해요.",
            "이걸 X년 전에 알았다면…",
        ],
        "example": (
            "이거 모르면 1년에 50만원 그냥 버리는 거야.\n"
            "{product} 쓰기 전 매달 4만원씩 더 썼거든.\n"
            "1년이면 50만원, 5년이면 250만원.\n"
            "이번 달부터라도 바꾸면 다음 달부터 절약 시작.\n"
            "쿠팡 링크 설명란.\n"
            "지금 한 번만 보면 평생 절약."
        ),
    },
    "comparison_battle": {
        "label": "🥊 비교 배틀",
        "when": "경쟁 제품과 직접 대결",
        "hint": "A vs B 직접 비교, 수치/스펙 명확히",
        "openers": [
            "{product} vs 1위 제품 직접 비교했어.",
            "유명 브랜드 거랑 같이 써봤어.",
            "둘 다 사봤는데 결론 알려줄게.",
        ],
        "example": (
            "{product} vs 유명 브랜드 직접 비교했어.\n"
            "가격: 2만원 vs 4만원, 절반.\n"
            "성능: 거의 동일, 차이 못 느낌.\n"
            "디자인: 솔직히 이게 더 깔끔.\n"
            "결론? 굳이 비싼 거 살 이유 없어.\n"
            "쿠팡 링크 설명란."
        ),
    },
    "before_after": {
        "label": "📸 Before-After",
        "when": "시각적 변화가 있는 카테고리 (뷰티/생활/다이어트)",
        "hint": "사용 전 / 후 명확히 대비",
        "openers": [
            "사용 전 vs 한 달 후 비교해봤어.",
            "이거 쓰기 전에는 진짜 심각했거든.",
            "전후 사진 보면 진짜 깜짝 놀라.",
        ],
        "example": (
            "사용 전: 매일 아침 따끔거리고 빨갰어.\n"
            "{product} 시작 후 2주: 진정되기 시작.\n"
            "한 달: 친구가 화장 바꿨냐고 물어봄.\n"
            "두 달: 피부과 약 끊음.\n"
            "지금: 이것 외엔 못 씀.\n"
            "쿠팡 링크 설명란."
        ),
    },
    "myth_buster": {
        "label": "🧨 통념 부수기",
        "when": "널리 알려진 상식 반박",
        "hint": "'다들 X라고 하는데 사실은 Y'",
        "openers": [
            "비싼 게 좋다는 건 거짓말이야.",
            "이거 다들 잘못 알고 있어.",
            "사실 비싼 브랜드일수록 더 위험해.",
        ],
        "example": (
            "비싼 거 = 좋은 거? 거짓말이야.\n"
            "{product} 2만원짜리가 10만원 브랜드보다 좋음.\n"
            "성분 비교표 직접 만들어봤어.\n"
            "오히려 비싼 게 첨가물 더 많아.\n"
            "마케팅비가 단가에 들어가는 거지.\n"
            "쿠팡 링크 설명란. 직접 봐."
        ),
    },
    "time_pressure": {
        "label": "⏱️ 시간 압박",
        "when": "한정 수량/할인 마감 등 진짜 긴급성 있을 때",
        "hint": "구체적 시간/수량 명시 (거짓 절대 금지)",
        "openers": [
            "오늘 할인 마지막이야.",
            "30개만 남음. 빨리 봐.",
            "이번 주 안에 결정해야 해.",
        ],
        "example": (
            "이거 가격 다음 주에 다시 오를 거야.\n"
            "{product} 지금 쿠팡에서 30% 할인 중.\n"
            "마감 임박이라 진짜 빨리 봐야 해.\n"
            "리뷰 5천 개에 4.8점.\n"
            "지금 이 가격 놓치면 내년에 후회.\n"
            "링크 설명란."
        ),
    },
    "expert_voice": {
        "label": "🎓 전문가/권위 인용",
        "when": "전문가/연구/기관 언급",
        "hint": "구체적 권위 (의사/논문/시험)",
        "openers": [
            "피부과 전문의가 추천한 제품.",
            "식약처 인증받은 거 중에서.",
            "국제 연구에서 1위 받은 성분.",
        ],
        "example": (
            "피부과 의사가 직접 추천한 제품이야.\n"
            "{product} 시카 70% 농도로 진정 효과 인증.\n"
            "성분표 보면 첨가물 거의 없음.\n"
            "임상 연구에서 84% 진정률.\n"
            "쿠팡 2만원대로 부담 없음.\n"
            "링크 설명란."
        ),
    },
    "raw_authentic": {
        "label": "🎙️ 진짜 솔직 톤",
        "when": "꾸미지 않은 일상 톤 (vlog/리뷰)",
        "hint": "단점도 함께 말하기, 신뢰 형성",
        "openers": [
            "솔직히 처음엔 별로였어.",
            "단점부터 말할게.",
            "이거 100% 만족은 아니야.",
        ],
        "example": (
            "단점부터 말할게. 향이 좀 있어.\n"
            "근데 그거 빼면 {product} 진짜 괜찮아.\n"
            "처음엔 흠칫했는데 한 달 쓰니까 적응됐어.\n"
            "효과는 확실해. 안 쓰면 다시 돌아감.\n"
            "단점 알고 사면 만족도 높음.\n"
            "쿠팡 링크 설명란."
        ),
    },

    # ── 🔥 도파민 폭발 패턴 (Z세대/2030 viral) ────────────────
    "instant_value": {
        "label": "⚡ 즉각 가치 폭발",
        "when": "1초 안에 결과/혜택 보여주기 (가장 강력한 viral)",
        "hint": "결론부터, 짧고 임팩트 있게. 첫 문장 10자 이내.",
        "openers": [
            "이거 1초만 봐.",
            "이거 보고 머리 멈춤.",
            "이거 알고 인생 바뀜.",
            "10초 안에 끝.",
        ],
        "example": (
            "이거 1초만 봐.\n"
            "{product} 실화임?\n"
            "원래 5만원인데 지금 1만원대.\n"
            "와 진짜 미쳤어.\n"
            "리뷰 4.9에 5천 개 넘음.\n"
            "쿠팡 로켓배송 내일 도착.\n"
            "링크 밑에. 진심 이건 사야 함."
        ),
    },
    "discovery_story": {
        "label": "👀 발견 스토리",
        "when": "우연히 알게 된 톤 (자연스러움 = 신뢰)",
        "hint": "친구/우연/SNS에서 본 척. 광고 같지 않게.",
        "openers": [
            "친구 폰에서 우연히 봤는데",
            "지나가다 본 건데 진심",
            "댓글 보고 사봤는데",
            "엄마가 쓰는 거 따라 사봤는데",
        ],
        "example": (
            "친구 폰에서 우연히 본 건데\n"
            "{product} 진짜 미쳤어.\n"
            "친구는 한 달 썼다는데 피부 결 봐봐.\n"
            "성분도 시카 70프로라 자극 없대.\n"
            "2만원대인데 200ml. 약국보다 쌈.\n"
            "나도 어제 시켰음. 링크 밑에."
        ),
    },
    "taboo_breaker": {
        "label": "🤐 금기 깨기",
        "when": "내부자/판매자/전문가가 안 알려주는 진실",
        "hint": "'사장님은 알리면 안 된다고 했어' 류 — 금기 + 호기심",
        "openers": [
            "사장님이 알리면 짤린다고 했어.",
            "원래 이렇게 쓰는 거 아니래 ㅋㅋ",
            "이거 비밀인데 진심 너만 알아.",
            "직원이 비싼 거 사지 말랬어.",
        ],
        "example": (
            "이거 비밀인데 너만 알아.\n"
            "올영 직원이 추천 안 한다는 그 토너.\n"
            "{product} 솔직히 비싼 거 살 필요 없대.\n"
            "성분 똑같은데 가격 절반.\n"
            "직원이 본인도 이거 쓴다고 함.\n"
            "쿠팡에 검색하면 바로 나와. 링크 밑에."
        ),
    },
    "z_casual": {
        "label": "🤙 Z세대 캐주얼",
        "when": "20대 친구처럼 자연스럽게 (가장 친근)",
        "hint": "ㅋㅋ, 진심, 미친, 와, 헐 등 Z세대 화법. 격식 0%.",
        "openers": [
            "와 진심 미친 거 아냐?",
            "헐 이거 뭐임 ㅋㅋ",
            "이거 진심 미쳤어.",
            "이런 거 진짜 처음 봄.",
        ],
        "example": (
            "와 이거 진심 미친 거 아냐?\n"
            "{product} 어제 처음 발라봤거든.\n"
            "오늘 거울 보고 헐 했음 ㅋㅋ\n"
            "민감 피부인데 따끔거림 0.\n"
            "친구가 화장 뭐 바꿨냐 함.\n"
            "쿠팡에 2만원대. 링크 밑에 박아둠."
        ),
    },
}


def list_patterns() -> list:
    """UI 선택용 [(id, label, when), ...]."""
    return [(pid, p["label"], p["when"]) for pid, p in VIRAL_PATTERNS.items()]


def get_pattern(pattern_id: str) -> dict:
    """알 수 없으면 첫 패턴 반환."""
    return VIRAL_PATTERNS.get(pattern_id, VIRAL_PATTERNS["shocking_stat"])


def format_pattern_brief(pattern_id: str, product: str = "") -> str:
    """LLM 프롬프트에 주입할 패턴 가이드 (간략)."""
    p = get_pattern(pattern_id)
    example = p["example"].replace("{product}", product) if product else p["example"]
    openers = " / ".join(f'"{o}"' for o in p["openers"])
    return (
        f"[패턴: {p['label']}]\n"
        f"- 활용 상황: {p['when']}\n"
        f"- 힌트: {p['hint']}\n"
        f"- 시작 예시: {openers}\n"
        f"- 전체 예시:\n{example}\n"
    )


def pick_three_patterns(category: str = "general", use_case: str = "coupang_affiliate") -> list:
    """카테고리/use case에 맞는 3가지 다른 패턴 추천.

    가장 다양성 있게 — 톤/구조가 서로 다른 3개 선택.
    """
    # 카테고리별 우선순위 — 도파민 폭발 패턴 우선 (Z세대 viral)
    priorities = {
        "beauty": ["instant_value", "z_casual", "discovery_story",
                    "personal_failure", "before_after", "taboo_breaker"],
        "food": ["instant_value", "shocking_stat", "z_casual",
                  "discovery_story", "comparison_battle"],
        "digital": ["instant_value", "comparison_battle", "shocking_stat",
                     "taboo_breaker", "z_casual"],
        "household": ["before_after", "instant_value", "discovery_story",
                       "z_casual", "fear_loss"],
        "fashion": ["z_casual", "discovery_story", "instant_value",
                     "countdown", "comparison_battle"],
        "baby_kids": ["personal_failure", "discovery_story", "expert_voice",
                       "instant_value"],
        "pet": ["z_casual", "discovery_story", "personal_failure",
                 "instant_value"],
        "general": ["instant_value", "z_casual", "discovery_story",
                     "shocking_stat", "taboo_breaker"],
    }
    candidates = priorities.get(category, priorities["general"])
    # 처음 3개 선택 (반복 없음)
    return candidates[:3]
