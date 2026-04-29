"""LLM-as-Judge — 생성된 대본을 객관적으로 평가하는 모듈.

전략 변경 (2026-04-27):
  대본 품질이 #1 우선순위. 키워드 매칭(eval_metrics)만으로는 부족.
  LLM judge가 5개 차원으로 0-100점 평가 → 점수 < 80이면 자동 재생성 트리거.

5개 평가 차원 (각 0-20점):
  1. Hook 임팩트: 첫 1.5초가 시청자 멈추게 하는가?
  2. 카테고리 적합성: 카테고리 가이드를 충실히 따르는가?
  3. 길이 적합성: 30초 음성 분량에 맞는가? (마크다운/메타 제외 본문 ≤ 220자)
  4. CTA 명확성: 행동 유도가 구체적인가?
  5. 구매 전환력: 시청자가 클릭할 만큼 욕구를 자극하는가?

비용:
  심사 1회 ≈ $0.005 (2K input + 200 output)
  영상 1개당 1-3회 (최초 + 재생성) → 영상당 약 $0.005-0.015 추가
"""
import json
import re
from typing import Optional

import api_keys
import eval_metrics


JUDGE_MODEL = "claude-sonnet-4-5"
DEFAULT_MIN_SCORE = 80
MAX_REGEN_ATTEMPTS = 3


JUDGE_SYSTEM = """당신은 쿠팡 파트너스 30초 쇼츠 대본을 평가하는 엄격한 광고 카피 심사위원입니다.
대본을 5개 차원으로 평가해 JSON으로만 답하세요.
설명 없이 JSON만 출력. 마크다운 코드블록 금지."""


JUDGE_USER_TEMPLATE = """다음 대본을 평가하세요. 5개 차원 모두 **반드시** 평가.
대본을 꼼꼼히 읽고 각 차원에 다른 점수를 주세요. 모든 차원에 같은 점수 금지.

[상품] {product}
[카테고리] {category}
[대본 시작]
{script}
[대본 끝]

각 0-20점 (합계 0-100):

1. **hook_impact** — 첫 문장이 시청자를 멈추게 하는가?
   18-20: 충격 사연/숫자/장면 (예: "응급실 갔던 사람", "1시간 영상 → 30초")
   13-17: 의문문/강한 단어 (예: "이거 진짜?")
   8-12: 일반적 (예: "이 제품 추천")
   0-7: 평범한 시작 (예: "안녕하세요")

2. **category_fit** — {category} 카테고리 고유 언어/패턴?
   18-20: 카테고리 특화 (뷰티=피부과/성분농도, 식품=가격비교/유통기한, 디지털=스펙/실측)
   13-17: 일부 카테고리 표현
   0-12: 일반 광고 카피

3. **specificity** — 구체적 수치/이름/사례 몇 개?
   18-20: 수치 2개+ (가격/스펙/시점) AND 사람/상황 1개+
   13-17: 수치 또는 사례 1-2개
   0-12: 일반론 ("좋아요/효과 있어요")

4. **anti_cliche** — ChatGPT 안전 톤 회피?
   18-20: 친구 카톡체, 클리셰 0개
   13-17: 일부 클리셰 ("지금 바로", "확인하세요")
   0-12: 전형 광고 카피, ChatGPT 냄새

5. **conversion_power** — 구매 욕구 자극력?
   18-20: 사회적 증거 + 가격/희소성 + 본인 대입 가능
   13-17: 욕구 자극 일부
   0-12: 약함

**total은 5개 점수 합산** (예: 17+15+19+18+16 = 85).
**80점 이상이면 PASS. 미만은 FAIL.**

JSON만 출력 (마크다운 코드블록 사용 금지, ```json도 금지):
{{
  "hook_impact":      {{"score": <int>, "reason": "<한 줄, 위 기준 어디 해당하는지>"}},
  "category_fit":     {{"score": <int>, "reason": "..."}},
  "specificity":      {{"score": <int>, "reason": "..."}},
  "anti_cliche":      {{"score": <int>, "reason": "..."}},
  "conversion_power": {{"score": <int>, "reason": "..."}},
  "total": <int>,
  "verdict": "PASS" 또는 "FAIL",
  "improvement": "<재생성 시 어디부터 고쳐야 할지 구체적 1가지>"
}}"""


def judge_script(script: str, product: str = "", category: str = "general",
                 use_case: str = "coupang_affiliate",
                 min_score: int = DEFAULT_MIN_SCORE) -> dict:
    """대본 1건을 LLM judge로 평가.

    Returns:
        {
            "ok": True/False,                # API 호출 성공 여부
            "scores": {hook_impact: {...}, ...},
            "total": int,
            "verdict": "PASS" | "FAIL",
            "improvement": str,
            "passed": bool                    # total >= min_score
        }
    """
    api_key = api_keys.get_api_key("ANTHROPIC_API_KEY")
    if not api_key:
        # 폴백: eval_metrics 기반 간이 점수 (API 키 없을 때)
        return _fallback_judge(script, min_score)

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        user_msg = JUDGE_USER_TEMPLATE.format(
            product=product or "(미상)",
            category=category or "general",
            script=script[:2000],  # 토큰 절약
        )
        response = client.messages.create(
            model=JUDGE_MODEL, max_tokens=600,
            system=JUDGE_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        )
        text = response.content[0].text.strip()
        parsed = _parse_judge_json(text)
        if not parsed:
            return _fallback_judge(script, min_score)
        # 신구 차원 모두 시도 (호환성)
        new_dims = ("hook_impact", "category_fit", "specificity",
                     "anti_cliche", "conversion_power")
        old_dims = ("hook_impact", "category_fit", "length_fit",
                     "cta_clarity", "conversion_power")
        # 신차원 우선, 없으면 구차원
        scores = {k: parsed.get(k, {}) for k in new_dims}
        if not any(s.get("score") for s in scores.values()):
            scores = {k: parsed.get(k, {}) for k in old_dims}
        # use case 가중치 적용 — 단순 합 vs 가중 평균 둘 다 제공
        try:
            import use_cases as _uc
            total_weighted = _uc.weighted_judge_score(scores, use_case)
        except Exception:
            total_weighted = float(parsed.get("total", 0))
        total_simple = int(parsed.get("total", 0))
        # 채택 점수 = 가중 평균 (use case별 우선순위 반영)
        total = int(round(total_weighted))
        return {
            "ok": True,
            "use_case": use_case,
            "scores": scores,
            "total": total,
            "total_simple": total_simple,
            "total_weighted": total_weighted,
            "verdict": "PASS" if total >= min_score else "FAIL",
            "improvement": parsed.get("improvement", ""),
            "passed": total >= min_score,
        }
    except Exception:
        return _fallback_judge(script, min_score)


def _parse_judge_json(text: str) -> Optional[dict]:
    """응답에서 JSON 블록 추출 (마크다운 등으로 감싸도 OK)."""
    # ```json ... ``` 또는 그냥 {...}
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _fallback_judge(script: str, min_score: int) -> dict:
    """API 키 없거나 호출 실패 시 — eval_metrics 기반 간이 평가."""
    m = eval_metrics.evaluate_script(script)
    # 단순 환산: hook_score(0-3) → 0-20, has_cta → 0/20, 길이 적합 → 0/20
    hook_pts = (m["hook_score"] / 3) * 20
    cat_pts = 12  # 가이드 미적용 가정
    body_len = m["char_len"]
    if 150 <= body_len <= 250:
        len_pts = 20
    elif 100 <= body_len < 150 or 250 < body_len <= 350:
        len_pts = 12
    else:
        len_pts = 5
    cta_pts = 20 if m["has_cta"] else 5
    conv_pts = 12  # LLM 없이 평가 불가, 평균값
    total = int(hook_pts + cat_pts + len_pts + cta_pts + conv_pts)
    return {
        "ok": False,  # 폴백 표시
        "scores": {
            "hook_impact": {"score": int(hook_pts), "reason": "키워드 기반 추정"},
            "category_fit": {"score": cat_pts, "reason": "LLM 평가 불가, 평균"},
            "length_fit": {"score": len_pts, "reason": f"{body_len}자"},
            "cta_clarity": {"score": cta_pts, "reason": "CTA 키워드 유무"},
            "conversion_power": {"score": conv_pts, "reason": "LLM 평가 불가, 평균"},
        },
        "total": total,
        "verdict": "PASS" if total >= min_score else "FAIL",
        "improvement": "ANTHROPIC_API_KEY 설정 시 정밀 평가 가능",
        "passed": total >= min_score,
    }


def generate_with_quality_loop(generate_fn, product: str, category: str,
                                 use_case: str = "coupang_affiliate",
                                 min_score: int = DEFAULT_MIN_SCORE,
                                 max_attempts: int = MAX_REGEN_ATTEMPTS) -> dict:
    """대본 자동 재생성 루프 — 점수 < min_score면 재시도.

    Args:
        generate_fn: () -> str 또는 (improvement_hint: str) -> str
                     (재시도 시 직전 judge의 improvement를 힌트로 받을 수 있음)
        product: 상품명 (judge 컨텍스트)
        category: 카테고리 ID
        min_score: 합격선 (기본 80)
        max_attempts: 최대 재시도 횟수

    Returns:
        {
            "script": str,           # 최종 채택 대본
            "judge": dict,           # 최종 judge 결과
            "attempts": int,         # 시도 횟수
            "history": list,         # 매 시도의 (score, improvement)
            "passed": bool,
        }
    """
    history = []
    best_script = None
    best_result = None
    best_score = -1

    for attempt in range(1, max_attempts + 1):
        improvement_hint = (history[-1]["improvement"] if history else "")
        # generate_fn이 hint 받는 시그니처인지 자동 판별
        try:
            script = generate_fn(improvement_hint) if improvement_hint else generate_fn("")
        except TypeError:
            script = generate_fn()
        if not script:
            history.append({"attempt": attempt, "score": 0, "improvement": "생성 실패"})
            continue
        result = judge_script(script, product=product, category=category,
                                use_case=use_case, min_score=min_score)
        history.append({
            "attempt": attempt,
            "score": result["total"],
            "improvement": result.get("improvement", ""),
        })
        if result["total"] > best_score:
            best_script = script
            best_result = result
            best_score = result["total"]
        if result["passed"]:
            break

    return {
        "script": best_script or "",
        "judge": best_result or {},
        "attempts": len(history),
        "history": history,
        "passed": (best_result or {}).get("passed", False),
    }
