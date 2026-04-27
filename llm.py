"""LLM 호출 단일 진입점 (Phase 2 모듈 분리 #2).

call_claude:
  - Anthropic Messages API 래퍼
  - eval_metrics 자동 로깅 (실패해도 흐름 안 막음)
  - UI 비의존: 에러는 on_error 콜백으로만 전달 (없으면 조용히 None 반환)

translate_keyword_to_english:
  - Pexels 검색용 영어 키워드 변환 (이미 영어면 그대로)

설계:
  - app.py(streamlit)에서는 on_error로 st.error 주입
  - 단위 테스트에서는 on_error 없이 호출 → 순수 함수처럼 동작
"""
import re
import time
from typing import Callable, Optional

import api_keys
import eval_metrics


CLAUDE_MODEL = "claude-sonnet-4-20250514"


def call_claude(system_prompt: str, user_msg: str, max_tokens: int = 1500,
                prompt_type: str = "generic",
                on_error: Optional[Callable[[Exception], None]] = None) -> Optional[str]:
    """Claude Messages API 호출 + 메트릭 자동 로깅."""
    api_key = api_keys.get_api_key("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        t0 = time.time()
        m = client.messages.create(
            model=CLAUDE_MODEL, max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_msg}],
        )
        text = m.content[0].text.strip()
        try:
            eval_metrics.log_llm_call(
                prompt_type=prompt_type, model=CLAUDE_MODEL,
                response=text, prompt_chars=len(system_prompt) + len(user_msg),
                latency_ms=int((time.time() - t0) * 1000),
            )
        except Exception:
            pass
        return text
    except Exception as e:
        if on_error:
            try:
                on_error(e)
            except Exception:
                pass
        return None


_ENGLISH_RE = re.compile(r"^[a-zA-Z0-9\s\-]+$")


def translate_keyword_to_english(keyword: str) -> str:
    """한국어 키워드를 Pexels 검색용 영어로 변환. 이미 영어면 그대로."""
    if not keyword:
        return ""
    if _ENGLISH_RE.match(keyword.strip()):
        return keyword
    result = call_claude(
        "Translate the following Korean keyword to English for Pexels stock video search. "
        "Output ONLY the English keyword (2-3 words max), nothing else.",
        keyword, max_tokens=30, prompt_type="translate_keyword",
    )
    return result.strip() if result else keyword
