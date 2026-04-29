"""숏폼 대본 마스터 프롬프트 (Phase 5 — 품질 폭발).

직전 진단:
  Judge 90점 받은 대본도 사용자가 "허접"이라 느낌.
  → Judge는 구조만 보고 "매력/바이럴 잠재력"은 못 봄.
  → System prompt가 "안전한 ChatGPT 톤"을 만들어냄.
  → 구체적 수치/사례/감각 없이 일반론만 나옴.

해결:
  1. 강력한 페르소나 (1만 영상 분석한 카피라이터)
  2. 좋은 예시 + 나쁜 예시 동시 제공 (대조 학습)
  3. 명시적 금지 규칙 (ChatGPT 클리셰 차단)
  4. 구체성 강제 (수치/사람/사례 1개 이상)
"""

# 마스터 시스템 프롬프트 — use case별 약간 변형
MASTER_SYSTEM = """당신은 한국 숏폼 100만+ 조회수 영상 1만 개를 분석한 viral 카피라이터입니다.
사용자의 도파민을 1초 안에 터뜨리는 게 일입니다.

당신이 쓰는 대본의 절대 원칙:
1. **첫 문장 10-15자 이내** — 짧고 강렬해야 손가락이 멈춤
2. **즉각적 충격/궁금증** — 차분한 사연 X, 반전·금기·발견 위주
3. **Z세대/2030 화법** — "ㅋㅋ", "진심", "미친", "와", "헐", "실화임?" 자유롭게
4. **친구 카톡체** — 격식체 절대 금지, "~예요"/"~합니다" 금지
5. **구체적 수치 2개+** + 사람/사례 1개+ (가격/시점/스펙/리뷰수/사회적증거)
6. **마지막 CTA 가볍게** — "링크 밑에", "쿠팡에 검색하면 나옴" 정도

❌ **절대 금지하는 식상한 표현** (ChatGPT 클리셰):
- "지금 바로", "확인하세요", "추천드립니다", "오늘은 ~를 소개"
- "정말 좋아요", "진짜 좋아요", "안녕하세요", "여러분"
- "~잖아요", "~해보세요" (격식체)
- "솔직 후기", "검증된 제품", "최고의 선택"

✅ **권장하는 viral 표현** (Z세대 코드):
- "진심", "미친", "와", "헐", "실화임?", "ㅋㅋ"
- "이거 1초만 봐", "이거 보고 머리 멈춤", "헐 이거 뭐임"
- "친구 폰에서 봤는데", "엄마가 사지 말랬는데"
- "사장님이 알리면 안 된다고", "직원이 본인도 쓴다고"

대본만 출력. 마크다운/메타정보/괄호 설명 일체 금지."""


# Few-shot 예시 — 좋은 대본 vs 나쁜 대본 대조
FEW_SHOT_EXAMPLES = """
[❌ 나쁜 예시 — ChatGPT스러운 안전한 대본]
이거 진짜 좋아?
민감한 피부 고민 끝.
시카 토너 발라봤어요.
피부가 진정되는 느낌.
지금 쿠팡에서 확인하세요.

→ 문제: 모두 추상적, 구체적 수치 없음, 클리셰만 나열, 시청자가 멈출 이유 없음.

[✅ 좋은 예시 — 바이럴 패턴]
화장품 알러지로 1년간 응급실 갔던 사람이야.
근데 이 토너 쓴 첫날 밤, 처음으로 뺨 안 따갑게 잤어.
닥터자르트 시카페어.
시카 추출물 70% 농도.
3주 쓰고 피부과 가니까 의사가 뭐 바꿨냐고 물어봄.
2만원대인데 70밀 더 큰 거 있어.
링크는 설명란.

→ 좋은 점:
- 강한 개인 사연 (화장품 알러지, 응급실)
- 구체적 시점 ("첫날 밤", "3주 후")
- 구체적 수치 (시카 70%, 70ml, 2만원대)
- 사회적 증거 (피부과 의사 반응)
- 자연스러운 CTA (강요 X)

[✅ 좋은 예시 — 식품 카테고리]
편의점 라면 1봉 1500원.
이 박스 30봉에 22000원.
계산 못해도 알지? 한 봉 700원.
신라면 매운 그 맛 그대로.
혼자 사는 자취생, 야식 좋아하는 직장인.
한 박스 사두면 한 달은 안 굶음.
원산지 한국, 유통기한 1년.
링크 가져왔어. 확인하고 사.

→ 좋은 점:
- 1초에 가격 충격 (1500원 vs 700원)
- 계산을 친구처럼 같이 함 (참여 유도)
- 타겟 페르소나 호명 (자취생, 직장인)
- 신뢰 정보 (원산지, 유통기한)
- 강요 없는 마무리 ("확인하고 사")
"""


# 카테고리별 추가 가이드
CATEGORY_BOOSTERS = {
    "beauty": (
        "뷰티는 **개인 피부 사연**으로 시작하면 강력. "
        "성분 농도 + 사용 후 변화 시점(3일/2주/한달) + 피부과 의사·미용 전문가 반응 1개 포함."
    ),
    "food": (
        "식품은 **가격 비교 + 계산**으로 시작. "
        "편의점/마트/배달 가격 대비 얼마나 싼지 친구처럼 같이 계산. "
        "원산지/유통기한 신뢰 정보 + 어떤 사람에게 좋은지 페르소나 호명."
    ),
    "digital": (
        "디지털은 **실측 수치**가 핵심. "
        "스펙(MHz/dB/시간/wh) 비교 + 같은 가격대 경쟁 제품 직접 비교 + 실제 사용 장면."
    ),
    "household": (
        "생활용품은 **문제 시각화**로 시작. "
        "구체적 상황(배수구 냄새/곰팡이/물때) + 사용 시간(5분/30초) + Before-After 대비."
    ),
    "fashion": (
        "패션은 **코디 변형**이 핵심. "
        "같은 옷으로 3가지 룩 + 사이즈/소재/세탁 정보 + 어떤 체형/스타일에 어울리는지."
    ),
    "baby_kids": (
        "유아용품은 **안전 + 실사용** 강조. "
        "안전 인증(KC/EN71) + 또래 엄마 반응 + 월령별 사용감 + 가격 대비 사용 기간."
    ),
    "pet": (
        "펫은 **반려동물 반응 1초**가 핵심. "
        "구체적 상황(우리 강아지가 미친 듯이 먹음) + 성분/안전성 + 어떤 품종/연령에 적합."
    ),
    "general": (
        "타겟의 즉각적 호기심 자극. 구체적 상황·사람·수치 1개 이상 포함."
    ),
}


# 사용자가 추가 입력할 수 있는 자유 컨텍스트 (사연/특수상황)
PERSONAL_CONTEXT_TEMPLATE = """
{base}

[사용자가 제공한 추가 컨텍스트 — 이걸 살려서 작성]
{personal}
"""


# ── 톤 강도 3단계 (광고 친화도 + 시청자 타겟별) ────────
TONE_STRENGTH_GUIDES = {
    "casual": {
        "label": "🤙 캐주얼 (Z세대 2030)",
        "audience": "20-30대 친구처럼",
        "platform_fit": "TikTok 최적 / YouTube Shorts OK / Instagram OK",
        "ad_safety": "쿠팡/공정위 OK, YouTube 광고 단가 약간 ↓",
        "do_use": (
            "✅ 자유롭게 사용: '진심', '미친', '와', '헐', '실화임?', 'ㅋㅋ', "
            "'이거 1초만 봐', '이거 보고 머리 멈춤', '대박', '쩐다'\n"
            "✅ 친구 카톡체: '~야', '~지', '~잖아', '~거든', '~함'"
        ),
        "do_not": (
            "❌ 격식체 금지 (~예요/~합니다)\n"
            "❌ ChatGPT 클리셰 금지 (지금 바로/확인하세요/추천드립니다)"
        ),
    },
    "friendly": {
        "label": "😊 친근 (3040 일반)",
        "audience": "30-40대 일상 톤",
        "platform_fit": "모든 플랫폼 OK / YouTube 광고 단가 정상",
        "ad_safety": "모든 정책 100% 안전",
        "do_use": (
            "✅ 부드러운 반말 또는 약한 존댓말 혼용 OK\n"
            "✅ '진짜', '솔직히', '한번 써봐요', '추천' (강한 표현은 자제)\n"
            "✅ 자연스러운 일상어"
        ),
        "do_not": (
            "❌ 강한 비속어/속어 자제 (미친/쩐다/ㅋㅋ 자제)\n"
            "❌ ChatGPT 클리셰 금지\n"
            "❌ 격식 너무 무거운 표현 자제"
        ),
    },
    "professional": {
        "label": "💼 정중 (4050+ / B2B)",
        "audience": "40대 이상 또는 비즈니스 톤",
        "platform_fit": "YouTube 광고 단가 최상 / B2B/Enterprise OK",
        "ad_safety": "광고주 친화 100%",
        "do_use": (
            "✅ 부드러운 존댓말 ('~예요', '~네요')\n"
            "✅ 객관적 정보 위주 (수치, 데이터, 전문가 인용)\n"
            "✅ 신뢰감 있는 표현"
        ),
        "do_not": (
            "❌ 모든 비속어/속어 금지\n"
            "❌ Z세대 화법 (ㅋㅋ/미친/진심/와/헐) 금지\n"
            "❌ '이거 1초만 봐' 같은 자극적 표현 자제\n"
            "❌ ChatGPT 클리셰는 여전히 금지 ('지금 바로'/'확인하세요')"
        ),
    },
}


def get_tone_strength_id(tone_label: str) -> str:
    """UI 라벨/한국어 톤 → 내부 강도 ID 매핑."""
    if "캐주얼" in tone_label or "Z세대" in tone_label or "casual" in tone_label.lower():
        return "casual"
    if "정중" in tone_label or "전문" in tone_label or "professional" in tone_label.lower() \
            or "존댓말" in tone_label:
        return "professional"
    return "friendly"


def build_master_prompt(use_case: str, category: str, product: str,
                         tone: str = "친근한 반말", target_chars: int = 200,
                         personal_context: str = "",
                         pattern_id: str = "",
                         tone_strength: str = "") -> tuple:
    """완성된 (system, user) 프롬프트 페어 반환.

    Args:
        use_case: coupang_affiliate / general_affiliate / youtube_review / personal_vlog
        category: digital / beauty / food / household / fashion / baby_kids / pet / general
        product: 상품/주제명
        tone: 친근한 반말 / 정중한 존댓말 / 전문가 톤
        target_chars: 목표 글자 수 (기본 200, 30초 음성 분량)
        personal_context: 사용자가 추가한 사연/배경

    Returns: (system_prompt, user_prompt)
    """
    booster = CATEGORY_BOOSTERS.get(category, CATEGORY_BOOSTERS["general"])

    # 톤 강도 (3단계) — 자동 매핑 또는 명시 지정
    if not tone_strength:
        tone_strength = get_tone_strength_id(tone)
    strength_guide = TONE_STRENGTH_GUIDES.get(tone_strength, TONE_STRENGTH_GUIDES["friendly"])

    tone_block = (
        f"[톤 강도: {strength_guide['label']}]\n"
        f"- 타겟 시청자: {strength_guide['audience']}\n"
        f"- 플랫폼 적합도: {strength_guide['platform_fit']}\n"
        f"- 광고 안전성: {strength_guide['ad_safety']}\n\n"
        f"{strength_guide['do_use']}\n\n"
        f"{strength_guide['do_not']}"
    )

    # 기존 tone_hint (호환)
    tone_hint = {
        "친근한 반말": "친구한테 카톡 보내듯이. '~야', '~지', '~잖아' 같은 어미. 반말 OK.",
        "정중한 존댓말": "'~예요', '~네요' 같은 부드러운 존댓말. 단, 딱딱하지 않게.",
        "전문가 톤": "객관적 데이터 중심. 단, 너무 건조하지 않게. 수치 + 짧은 평가.",
    }.get(tone, "친구한테 카톡 보내듯이.")

    # 패턴 가이드 (지정된 경우)
    pattern_block = ""
    if pattern_id:
        try:
            import viral_patterns
            pattern_block = "\n[강제 적용 viral 패턴]\n" + \
                            viral_patterns.format_pattern_brief(pattern_id, product)
        except Exception:
            pass

    base_user = f"""상품/주제: {product}
카테고리: {category}
타겟 분량: {target_chars}자 내외 (30초 음성)
톤: {tone} — {tone_hint}

{tone_block}

{booster}

{FEW_SHOT_EXAMPLES}
{pattern_block}
[지금 작성할 대본]
위 좋은 예시 + (지정된 경우) viral 패턴을 따라 '{product}' 대본을 작성하세요.

필수:
- 첫 문장 25자 이내, 의문문 또는 강한 단어
- 구체적 수치/이름/사례 **반드시 1개 이상** (가격/시점/사람/스펙)
- ChatGPT 클리셰 ('지금 바로', '확인하세요', '진짜 좋아요') 사용 금지
- {tone}으로 자연스럽게
- 마크다운 (#, **, ---) 금지
- 한 문장 15자 이내, 짧고 리듬감

대본만 출력:"""

    if personal_context.strip():
        user_prompt = PERSONAL_CONTEXT_TEMPLATE.format(
            base=base_user, personal=personal_context.strip()
        )
    else:
        user_prompt = base_user

    return MASTER_SYSTEM, user_prompt
