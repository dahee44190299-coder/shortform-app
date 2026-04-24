"""평가 데이터셋 실행 CLI (Phase 1-C).

사용:
  python run_eval.py                     # 카테고리 추론 정확도만
  python run_eval.py --llm               # + LLM 스크립트 생성 메트릭 (API 키 필요)

출력:
  - 카테고리 추론: 케이스별 pass/fail + 전체 정확도
  - LLM 메트릭: 평균 char_len, has_hook 비율, has_cta 비율 등

종료 코드: 카테고리 정확도 < 80% 면 1, 아니면 0 (CI 사용 가능).
"""
import json
import os
import sys
import time

import category_templates


def load_cases(path: str = "eval_data/eval_cases.json") -> list:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f).get("cases", [])


def eval_category_inference(cases: list, verbose: bool = False) -> dict:
    correct = 0
    fails = []
    by_cat: dict = {}
    for c in cases:
        title = c.get("product_title", "")
        expected = c.get("expected_category", "general")
        actual = category_templates.infer_category(title)
        ok = (actual == expected)
        if ok:
            correct += 1
        else:
            fails.append({"id": c.get("id"), "title": title,
                          "expected": expected, "actual": actual})
        by_cat.setdefault(expected, {"total": 0, "correct": 0})
        by_cat[expected]["total"] += 1
        if ok:
            by_cat[expected]["correct"] += 1
        if verbose:
            mark = "OK " if ok else "FAIL"
            print(f"  [{mark}] {c.get('id')} expected={expected} actual={actual} | {title[:50]}")
    n = len(cases)
    acc = (correct / n * 100) if n else 0.0
    return {
        "total": n,
        "correct": correct,
        "accuracy_pct": round(acc, 1),
        "by_category": by_cat,
        "failures": fails,
    }


def eval_llm_quality(cases: list, sample: int = 5) -> dict:
    """LLM이 생성하는 스크립트 품질 메트릭. API 키 없으면 skip."""
    try:
        import anthropic
    except ImportError:
        return {"skipped": True, "reason": "anthropic 패키지 미설치"}
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        try:
            import tomllib
            with open(".streamlit/secrets.toml", "rb") as f:
                api_key = tomllib.load(f).get("ANTHROPIC_API_KEY", "")
        except Exception:
            pass
    if not api_key:
        return {"skipped": True, "reason": "ANTHROPIC_API_KEY 미설정"}

    import eval_metrics

    client = anthropic.Anthropic(api_key=api_key)
    model = "claude-sonnet-4-20250514"
    sampled = cases[:sample]
    results = []
    for c in sampled:
        title = c.get("product_title", "")
        cat = c.get("expected_category", "general")
        hint = category_templates.format_category_hint(cat)
        system = "당신은 쿠팡 파트너스 30초 쇼츠 스크립트 작가입니다. 한국어로 답하세요."
        user = (
            f"상품: {title}\n\n{hint}\n"
            f"30초 쇼츠 대본을 작성하세요. Hook(1초) → 본문(20초) → CTA(5초) 구조."
        )
        t0 = time.time()
        try:
            m = client.messages.create(
                model=model, max_tokens=600, system=system,
                messages=[{"role": "user", "content": user}],
            )
            text = m.content[0].text.strip()
        except Exception as e:
            results.append({"id": c.get("id"), "error": str(e)[:100]})
            continue
        latency = int((time.time() - t0) * 1000)
        eval_metrics.log_llm_call(
            prompt_type="eval_script", model=model, response=text,
            prompt_chars=len(user), latency_ms=latency,
            extra={"eval_case_id": c.get("id"), "category": cat},
        )
        metrics = eval_metrics.evaluate_script(text)
        results.append({"id": c.get("id"), "category": cat, "metrics": metrics, "latency_ms": latency})
    return {"sampled": len(sampled), "results": results}


def main():
    args = sys.argv[1:]
    verbose = "--verbose" in args or "-v" in args
    do_llm = "--llm" in args

    cases = load_cases()
    print(f"=== 평가 데이터셋 로드: {len(cases)}개 ===\n")

    print("--- 1) 카테고리 추론 정확도 ---")
    cat_result = eval_category_inference(cases, verbose=verbose)
    print(f"  정확도: {cat_result['accuracy_pct']}% ({cat_result['correct']}/{cat_result['total']})")
    print("  카테고리별:")
    for cat, st in sorted(cat_result["by_category"].items()):
        acc = (st["correct"] / st["total"] * 100) if st["total"] else 0
        print(f"    {cat:12s}  {st['correct']}/{st['total']}  ({acc:.1f}%)")
    if cat_result["failures"]:
        print(f"  실패 {len(cat_result['failures'])}건:")
        for f in cat_result["failures"][:10]:
            print(f"    - {f['id']}: expected={f['expected']} actual={f['actual']} | {f['title'][:50]}")
        if len(cat_result["failures"]) > 10:
            print(f"    ... + {len(cat_result['failures']) - 10}건")

    if do_llm:
        print("\n--- 2) LLM 스크립트 품질 메트릭 ---")
        llm_result = eval_llm_quality(cases, sample=5)
        if llm_result.get("skipped"):
            print(f"  스킵: {llm_result['reason']}")
        else:
            for r in llm_result["results"]:
                if "error" in r:
                    print(f"  [{r['id']}] ERROR: {r['error']}")
                    continue
                m = r["metrics"]
                print(f"  [{r['id']}] cat={r['category']:10s} chars={m['char_len']:4d} "
                      f"hook={m['has_hook']} cta={m['has_cta']} latency={r['latency_ms']}ms")

    sys.exit(0 if cat_result["accuracy_pct"] >= 80 else 1)


if __name__ == "__main__":
    main()
