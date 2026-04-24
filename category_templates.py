"""카테고리별 검증된 템플릿 (Phase 1-C).

쿠팡 파트너스 영상에서 잘 나가는 영상은 카테고리마다 패턴이 뚜렷하게 다름:
- 디지털/가전: 스펙 비교 + 실측치
- 뷰티: Before/After 비주얼
- 식품: 만족도 표정 + 가격 강조
- 생활용품: 문제→해결 시나리오
- 패션: 코디 변형 + 가격 대비

여기서 카테고리별 Hook/구조/CTA 가이드를 제공해 LLM 프롬프트를 강화한다.
사용자가 카테고리를 직접 고르거나, infer_category()가 상품명/URL에서 자동 추론.

Why 해자:
다른 도구는 "범용 Hook"만 제공. 우리는 카테고리별 검증된 패턴을 강제 주입.
인터뷰/실데이터로 패턴이 채워질수록 격차 확대 (Phase 2 데이터 해자의 시드).
"""


CATEGORY_PROFILES = {
    "digital": {
        "label": "디지털/가전",
        "keywords": ["이어폰", "노트북", "모니터", "키보드", "마우스", "충전기", "충전",
                     "스피커", "헤드폰", "에어팟", "아이폰", "갤럭시",
                     "tv", "tablet", "태블릿", "전자", "usb", "스마트워치",
                     "거치대", "무선충전"],
        "hook_pattern": "구체적 수치로 시작 (예: '3만원에 이 스펙?')",
        "structure": "1) 가격/스펙 충격 → 2) 핵심 비교 1가지 → 3) 실측 사용 장면 → 4) 한 줄 결론",
        "cta": "스펙 더 보려면 설명란 링크 — 같은 가격대 비교 포함",
        "do_not": ["과장된 '인생템' 표현", "비교 대상 없는 '최고'", "허위 할인율"],
    },
    "beauty": {
        "label": "뷰티/스킨케어",
        "keywords": ["로션", "크림", "토너", "선크림", "립스틱", "쿠션",
                     "파운데이션", "섀도우", "마스카라", "샴푸", "트리트먼트",
                     "에센스", "세럼", "시트마스크", "마스크", "스킨케어", "메이크업"],
        "hook_pattern": "Before 상태를 1초 노출 (예: '이 모공이 진짜 사라질까?')",
        "structure": "1) 문제 시각화 → 2) 사용 장면 → 3) After 비교 → 4) 가격/사용감",
        "cta": "내 피부 타입에 맞는지 설명란 체크 후 구매",
        "do_not": ["의학적 효능 단정", "특정 인종/외모 비하", "성분 검증 없는 단정"],
    },
    "food": {
        "label": "식품/건강",
        "keywords": ["과자", "라면", "신라면", "음료", "커피", "녹차", "홍차", "초콜릿", "사탕",
                     "과일", "고기", "치킨", "피자", "도시락", "냉동", "간편식", "영양제",
                     "비타민", "프로틴", "단백질", "다이어트", "음식", "면", "닭가슴살",
                     "만두", "홍삼"],
        "hook_pattern": "맛/가격 비교 한 문장 (예: '편의점 3배 가격, 맛도 3배?')",
        "structure": "1) 만족도 표정 1초 → 2) 클로즈업 + 한 입 사운드 → 3) 가격/용량 → 4) 이런 사람에게",
        "cta": "유통기한/원산지 설명란 확인 후 구매",
        "do_not": ["허위 효능 (다이어트 단정)", "비교 대상 없는 '최고 맛'", "위생 문제 회피"],
    },
    "household": {
        "label": "생활용품",
        "keywords": ["청소", "세제", "수세미", "주방", "욕실", "변기", "배수구",
                     "냄새", "곰팡이", "정리", "수납", "후크", "선반", "쓰레기",
                     "주방용품", "욕실용품", "물때", "청소기", "공기청정기",
                     "헤파필터", "필터", "정수기"],
        "hook_pattern": "문제 상황 1초 (예: '배수구 냄새, 이거 하나로 끝?')",
        "structure": "1) 문제 장면 → 2) 사용 시연 → 3) After 비교 → 4) 가격/주기",
        "cta": "지금 할인 중인지 설명란 링크에서 확인",
        "do_not": ["역겨운 시각 자극 과도 사용", "효과 즉시 단정 (시간 단축 과장)"],
    },
    "fashion": {
        "label": "패션/잡화",
        "keywords": ["셔츠", "티셔츠", "바지", "원피스", "신발", "운동화",
                     "가방", "백팩", "지갑", "벨트", "모자", "스카프", "양말",
                     "속옷", "코디", "스타일", "샘소나이트", "쌤소나이트"],
        "hook_pattern": "코디 변형 1초 (예: '같은 옷 3가지 스타일?')",
        "structure": "1) 코디 1 → 2) 코디 2 → 3) 가격/사이즈/소재 → 4) 어디서 더 입을까",
        "cta": "사이즈/소재 설명란 확인 — 반품 정책 포함",
        "do_not": ["체형 비하", "가격만으로 '인생템' 단정", "사이즈 정보 누락"],
    },
    "baby_kids": {
        "label": "유아/아동",
        "keywords": ["아기", "유아", "아이", "어린이", "기저귀", "분유", "장난감",
                     "유모차", "카시트", "젖병", "이유식", "아동복", "동화", "교구"],
        "hook_pattern": "안전/실용 한 문장 (예: '엄마들이 다 산다는 그 이유')",
        "structure": "1) 사용 장면 → 2) 안전 인증/소재 → 3) 가격/구성 → 4) 후기 요약",
        "cta": "월령/안전 인증 설명란 확인 후 구매",
        "do_not": ["발달 단정", "안전 인증 누락", "타 아이와 비교"],
    },
    "pet": {
        "label": "반려동물",
        "keywords": ["강아지", "고양이", "반려", "사료", "간식", "펫", "장난감",
                     "캣타워", "스크래쳐", "리드줄", "하네스", "방석", "급식기"],
        "hook_pattern": "반려동물 반응 1초 (예: '우리 고양이가 미쳐버린 그 간식')",
        "structure": "1) 동물 반응 → 2) 성분/용량 → 3) 가격/주기 → 4) 어떤 아이에게",
        "cta": "성분/알러지 설명란 확인 후 구매",
        "do_not": ["특정 품종 비하", "수의학적 단정", "안전성 검증 없는 단정"],
    },
    "general": {
        "label": "기타/일반",
        "keywords": [],
        "hook_pattern": "타겟의 즉각적 호기심 자극 (예: '이거 진짜?')",
        "structure": "1) Hook 1초 → 2) 핵심 가치 1가지 → 3) 시연/근거 → 4) CTA",
        "cta": "더 알아보려면 설명란 링크",
        "do_not": ["거짓 정보", "근거 없는 '최고'", "할인율 과장"],
    },
}


def infer_category(product_title: str = "", product_url: str = "") -> str:
    """상품명+URL에서 카테고리 자동 추론. 매칭 안 되면 'general'."""
    text = f"{product_title} {product_url}".lower()
    if not text.strip():
        return "general"
    best_id, best_hits = "general", 0
    for cid, prof in CATEGORY_PROFILES.items():
        if cid == "general":
            continue
        hits = sum(1 for kw in prof["keywords"] if kw in text)
        if hits > best_hits:
            best_id, best_hits = cid, hits
    return best_id


def get_template(category_id: str) -> dict:
    """카테고리 프로필 반환. 모르는 id면 general."""
    return CATEGORY_PROFILES.get(category_id, CATEGORY_PROFILES["general"])


def list_categories() -> list:
    """UI 드롭다운용 [(id, label), ...]."""
    return [(cid, prof["label"]) for cid, prof in CATEGORY_PROFILES.items()]


def format_category_hint(category_id: str) -> str:
    """LLM 프롬프트에 주입할 카테고리 가이드 블록."""
    prof = get_template(category_id)
    do_not_str = ", ".join(prof["do_not"])
    return (
        f"[카테고리: {prof['label']}]\n"
        f"- Hook 패턴: {prof['hook_pattern']}\n"
        f"- 영상 구조: {prof['structure']}\n"
        f"- CTA 권장: {prof['cta']}\n"
        f"- 금지사항: {do_not_str}\n"
    )
