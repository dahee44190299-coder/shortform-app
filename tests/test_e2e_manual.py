"""E2E 수동 검증 — 실제 LLM 호출 + 영상 파이프라인 일부.

⚠️ CI에서는 SKIP (ANTHROPIC_API_KEY 환경변수 또는 secrets 필요).
로컬에서 키 설정 후 직접 실행:

  pytest tests/test_e2e_manual.py -v -m e2e
  # 또는
  RUN_E2E=1 pytest tests/test_e2e_manual.py -v

체감 품질 검증 항목:
1. 카테고리 가이드가 실제 출력 품질에 영향을 주는가?
2. 메인 스크립트 생성 → has_hook + has_cta 모두 True인가?
3. 같은 카테고리에서 여러 번 생성 시 길이 편차는?
"""
import os
import statistics

import pytest

import api_keys
import category_templates
import eval_metrics
import llm


pytestmark = pytest.mark.skipif(
    not (os.getenv("RUN_E2E") or api_keys.get_api_key("ANTHROPIC_API_KEY")),
    reason="E2E 테스트는 ANTHROPIC_API_KEY 또는 RUN_E2E=1 필요",
)


SAMPLE_CASES = [
    {"title": "닥터자르트 시카페어 토너 200ml", "expected_cat": "beauty"},
    {"title": "농심 신라면 멀티팩 30봉", "expected_cat": "food"},
    {"title": "주방 배수구 냄새 제거 트랩", "expected_cat": "household"},
]


@pytest.mark.e2e
class TestCategoryGuideImpact:
    """카테고리 가이드 적용 vs 미적용 출력 비교."""

    def _gen_with_guide(self, title, cat):
        hint = category_templates.format_category_hint(cat)
        sys = "당신은 쿠팡 파트너스 30초 쇼츠 스크립트 작가입니다. 한국어로 답하세요."
        usr = (f"상품: {title}\n\n{hint}\n"
               f"30초 쇼츠 대본: Hook(1초) → 본문(20초) → CTA(5초).")
        return llm.call_claude(sys, usr, prompt_type="e2e_with_guide")

    def _gen_without_guide(self, title):
        sys = "당신은 쿠팡 파트너스 30초 쇼츠 스크립트 작가입니다. 한국어로 답하세요."
        usr = f"상품: {title}\n\n30초 쇼츠 대본: Hook(1초) → 본문(20초) → CTA(5초)."
        return llm.call_claude(sys, usr, prompt_type="e2e_without_guide")

    def test_with_guide_has_hook_and_cta(self):
        case = SAMPLE_CASES[0]
        out = self._gen_with_guide(case["title"], case["expected_cat"])
        assert out, "LLM 응답 None"
        m = eval_metrics.evaluate_script(out)
        assert m["has_hook"], f"Hook 감지 실패: {out[:200]}"
        assert m["has_cta"], f"CTA 감지 실패: {out[:200]}"

    def test_length_variance_within_category(self):
        """같은 카테고리에서 3번 생성 → 길이 편차 < 평균의 50%."""
        case = SAMPLE_CASES[1]
        lens = []
        for _ in range(3):
            out = self._gen_with_guide(case["title"], case["expected_cat"])
            assert out
            lens.append(len(out))
        mean = statistics.mean(lens)
        stdev = statistics.stdev(lens)
        # 너무 큰 편차는 프롬프트가 약하다는 신호
        assert stdev < mean * 0.5, f"길이 편차 큼: mean={mean}, stdev={stdev}, raw={lens}"
