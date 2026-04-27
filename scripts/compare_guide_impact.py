"""카테고리 가이드 적용 vs 미적용 — 실제 LLM 출력 비교.

각 카테고리에서 동일 상품 3회씩 with/without 생성 → 메트릭 비교.
ANTHROPIC_API_KEY 필요.

비용: 카테고리 5개 × 3회 × 2(with/without) = 30회 호출 ≈ $0.20 ~ $0.30
"""
import sys
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import api_keys
import category_templates
import eval_metrics
import llm


SAMPLES = [
    ("digital", "삼성 갤럭시 버즈3 프로 노이즈캔슬링"),
    ("beauty",  "닥터자르트 시카페어 토너 200ml"),
    ("food",    "농심 신라면 멀티팩 30봉"),
    ("household","주방 배수구 냄새 제거 트랩 6개입"),
    ("fashion", "유니클로 에어리즘 반팔 티셔츠"),
]
N_RUNS = 3


def _gen(title: str, cat: str | None) -> str:
    sys_prompt = "당신은 쿠팡 파트너스 30초 쇼츠 스크립트 작가입니다. 한국어로 답하세요."
    if cat:
        hint = category_templates.format_category_hint(cat)
        usr = f"상품: {title}\n\n{hint}\n30초 쇼츠 대본: Hook(1초) → 본문(20초) → CTA(5초)."
        ptype = "compare_with_guide"
    else:
        usr = f"상품: {title}\n\n30초 쇼츠 대본: Hook(1초) → 본문(20초) → CTA(5초)."
        ptype = "compare_no_guide"
    return llm.call_claude(sys_prompt, usr, prompt_type=ptype) or ""


def _aggregate(outputs: list) -> dict:
    if not outputs:
        return {}
    metrics = [eval_metrics.evaluate_script(o) for o in outputs]
    lens = [m["char_len"] for m in metrics]
    return {
        "n": len(outputs),
        "mean_chars": round(statistics.mean(lens), 1),
        "stdev_chars": round(statistics.stdev(lens), 1) if len(lens) > 1 else 0,
        "min_chars": min(lens),
        "max_chars": max(lens),
        "hook_rate": round(100 * sum(1 for m in metrics if m["has_hook"]) / len(metrics), 1),
        "cta_rate": round(100 * sum(1 for m in metrics if m["has_cta"]) / len(metrics), 1),
    }


def main():
    if not api_keys.get_api_key("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY 필요")
        sys.exit(1)

    print(f"=== 카테고리 가이드 영향 비교 ({len(SAMPLES)} 카테고리 × {N_RUNS}회 × 2조건) ===\n")
    rows = []
    for cat, title in SAMPLES:
        print(f"[{cat}] {title}")
        with_outputs, without_outputs = [], []
        for i in range(N_RUNS):
            with_outputs.append(_gen(title, cat))
            without_outputs.append(_gen(title, None))
            print(f"  run {i+1}/{N_RUNS} done")
        w = _aggregate(with_outputs)
        wo = _aggregate(without_outputs)
        rows.append((cat, w, wo))
        print(f"  With   guide: {w}")
        print(f"  Without guide: {wo}")
        print()

    # 종합
    print("=" * 80)
    print(f"{'cat':12} {'metric':18} {'WITH':>10} {'WITHOUT':>10} {'Δ':>10}")
    print("-" * 80)
    for cat, w, wo in rows:
        for k in ("mean_chars", "stdev_chars", "hook_rate", "cta_rate"):
            delta = w[k] - wo[k]
            sign = "+" if delta > 0 else ""
            print(f"{cat:12} {k:18} {w[k]:>10} {wo[k]:>10} {sign}{delta:>9}")
        print()

    # 평균
    avg_w_hook = statistics.mean(r[1]["hook_rate"] for r in rows)
    avg_wo_hook = statistics.mean(r[2]["hook_rate"] for r in rows)
    avg_w_cta = statistics.mean(r[1]["cta_rate"] for r in rows)
    avg_wo_cta = statistics.mean(r[2]["cta_rate"] for r in rows)
    avg_w_stdev = statistics.mean(r[1]["stdev_chars"] for r in rows)
    avg_wo_stdev = statistics.mean(r[2]["stdev_chars"] for r in rows)
    print(f"평균 Hook 포함률  with={avg_w_hook:.1f}% vs without={avg_wo_hook:.1f}% (Δ {avg_w_hook-avg_wo_hook:+.1f}%)")
    print(f"평균 CTA  포함률  with={avg_w_cta:.1f}% vs without={avg_wo_cta:.1f}% (Δ {avg_w_cta-avg_wo_cta:+.1f}%)")
    print(f"평균 길이 편차   with={avg_w_stdev:.1f} vs without={avg_wo_stdev:.1f}")


if __name__ == "__main__":
    main()
