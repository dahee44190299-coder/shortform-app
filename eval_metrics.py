"""평가 메트릭 모듈 (Phase 1-C).

LLM 호출 결과를 객관적 지표로 측정해 품질 편차를 가시화한다.
- evaluate_script(): 출력 1건의 정량 지표 (길이, Hook 유무, CTA 유무, ...)
- log_llm_call(): JSONL로 호출 이력 누적
- compute_stats(): 최근 N일치 통계 (평균/표준편차/최소/최대)

저장 경로: shortform_projects/_metrics/llm_calls.jsonl
JSONL 한 줄 = 호출 1건. 분석 도구 없이도 grep/jq로 분석 가능.

Why:
"같은 프롬프트인데 어떤 날은 좋고 어떤 날은 별로다" — 측정 못하면 개선도 없다.
편차가 크면 프롬프트 강화 또는 멀티 프로바이더 비교의 근거 데이터.
"""
import json
import os
import re
import statistics
from datetime import datetime, timezone, timedelta


METRICS_DIR = os.path.join("shortform_projects", "_metrics")
LLM_LOG_PATH = os.path.join(METRICS_DIR, "llm_calls.jsonl")


HOOK_INDICATORS = [
    # 강한 단어
    "진짜", "충격", "비밀", "이거", "왜", "어떻게", "사실", "솔직",
    "한 번", "한번", "꿀팁", "필수", "끝판왕", "대박", "미친",
    # 호기심/공감
    "혹시", "여러분", "다들", "저만", "저도",
    # 가격/혜택 임팩트
    "최저가", "할인", "공짜", "반값", "절반", "단돈",
    # 비교/순위
    "가장", "제일", "1위", "베스트", "비교",
]
CTA_INDICATORS = ["설명란", "링크", "댓글", "구독", "팔로우", "쿠팡", "할인", "구매",
                   "확인", "클릭", "프로필"]


def _strip_meta(text: str) -> str:
    """마크다운/메타정보 제거 후 본문만 추출 (Hook 평가의 정확도 향상).

    실측에서 Sonnet이 마크다운(#, **)으로 출력해서 첫 80자가 헤더로
    채워지는 경우 발견. 메타 제거 후 첫 줄을 Hook으로 본다.
    """
    cleaned = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        # 마크다운 헤더/구분자/볼드
        if s.startswith("#") or s.startswith("---") or s.startswith("==="):
            continue
        # 메타 키워드로 시작하는 줄
        if s.startswith(("**[", "[", "*", "**촬영", "**편집", "**음향", "**자막")):
            # [Hook], **[0-1초]** 같은 마커 제거
            stripped = re.sub(r"^[\*\[\]0-9초\-\s\|HhookOoOOK본문CTActa]+\*?\*?:?", "", s).strip()
            if stripped:
                cleaned.append(stripped)
            continue
        cleaned.append(s)
    return "\n".join(cleaned)


def _hook_strength(first_sentence: str) -> int:
    """Hook 1문장에 대한 0-3 점수.

    +1 짧음 (≤25자)
    +1 의문문 또는 감탄문
    +1 강한 단어 포함
    """
    if not first_sentence:
        return 0
    score = 0
    if len(first_sentence) <= 25:
        score += 1
    if "?" in first_sentence or "!" in first_sentence:
        score += 1
    if any(w in first_sentence for w in HOOK_INDICATORS):
        score += 1
    return score


def evaluate_script(text: str) -> dict:
    """스크립트 1건에 대한 정량 메트릭."""
    if not text:
        return {
            "char_len": 0, "word_count": 0, "sentence_count": 0,
            "has_hook": False, "has_cta": False, "has_question": False,
            "exclamations": 0, "lines": 0,
            "hook_score": 0, "first_sentence_len": 0,
        }
    body = _strip_meta(text) or text
    # 첫 문장 추출 — 구두점/줄바꿈을 만나면 끊되 구두점은 보존 (Hook 평가용)
    m = re.match(r"^([^\n.!?。]{1,120}[.!?。]?)", body.strip())
    first_sentence = (m.group(1) if m else body[:80]).strip()
    sentences = [s.strip() for s in re.split(r"[.!?。\n]+", body) if s.strip()]
    lines = [ln for ln in text.splitlines() if ln.strip()]
    first_chunk = body[:80]
    hook_score = _hook_strength(first_sentence)
    return {
        "char_len": len(text),
        "word_count": len(text.split()),
        "sentence_count": len(sentences),
        "has_hook": hook_score >= 2,  # 강화: 점수 2/3 이상이어야 has_hook
        "hook_score": hook_score,
        "first_sentence_len": len(first_sentence),
        "has_cta": any(t in text for t in CTA_INDICATORS),
        "has_question": "?" in first_chunk,
        "exclamations": text.count("!"),
        "lines": len(lines),
    }


def log_llm_call(prompt_type: str, model: str, response: str,
                 prompt_chars: int = 0, latency_ms: int = 0,
                 extra: dict | None = None) -> bool:
    """호출 1건을 JSONL에 append. 실패해도 앱 흐름 막지 않음."""
    try:
        os.makedirs(METRICS_DIR, exist_ok=True)
        metrics = evaluate_script(response or "")
        rec = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "prompt_type": prompt_type,
            "model": model,
            "prompt_chars": int(prompt_chars or 0),
            "latency_ms": int(latency_ms or 0),
            "response_chars": len(response or ""),
            "metrics": metrics,
        }
        if extra:
            rec["extra"] = extra
        with open(LLM_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def _load_records(days: int | None = None) -> list:
    if not os.path.exists(LLM_LOG_PATH):
        return []
    cutoff = None
    if days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    out = []
    with open(LLM_LOG_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if cutoff is not None:
                ts = rec.get("ts", "")
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    if dt < cutoff:
                        continue
                except (ValueError, TypeError):
                    continue
            out.append(rec)
    return out


def compute_stats(prompt_type: str | None = None, days: int | None = 7) -> dict:
    """최근 N일치 호출 통계.

    Returns:
      {
        "count": int,
        "by_prompt_type": {pt: count, ...},
        "metrics": {
          "char_len":   {"mean": ..., "stdev": ..., "min": ..., "max": ...},
          "word_count": {...},
          "has_hook_pct": float,
          "has_cta_pct": float,
        },
        "latency_ms": {"mean": ..., "stdev": ...},
      }
    """
    recs = _load_records(days=days)
    if prompt_type:
        recs = [r for r in recs if r.get("prompt_type") == prompt_type]
    n = len(recs)
    if n == 0:
        return {"count": 0, "by_prompt_type": {}, "metrics": {}, "latency_ms": {}}

    by_pt: dict = {}
    for r in recs:
        pt = r.get("prompt_type", "unknown")
        by_pt[pt] = by_pt.get(pt, 0) + 1

    char_lens = [int(r["metrics"]["char_len"]) for r in recs if "metrics" in r]
    word_counts = [int(r["metrics"]["word_count"]) for r in recs if "metrics" in r]
    latencies = [int(r.get("latency_ms", 0)) for r in recs]
    has_hooks = [1 if r["metrics"]["has_hook"] else 0 for r in recs if "metrics" in r]
    has_ctas = [1 if r["metrics"]["has_cta"] else 0 for r in recs if "metrics" in r]

    def _agg(xs):
        if not xs:
            return {"mean": 0, "stdev": 0, "min": 0, "max": 0}
        return {
            "mean": round(statistics.mean(xs), 1),
            "stdev": round(statistics.stdev(xs), 1) if len(xs) > 1 else 0,
            "min": min(xs),
            "max": max(xs),
        }

    return {
        "count": n,
        "by_prompt_type": by_pt,
        "metrics": {
            "char_len": _agg(char_lens),
            "word_count": _agg(word_counts),
            "has_hook_pct": round(100 * sum(has_hooks) / n, 1) if n else 0,
            "has_cta_pct": round(100 * sum(has_ctas) / n, 1) if n else 0,
        },
        "latency_ms": _agg(latencies),
    }
