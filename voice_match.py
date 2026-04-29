"""사용자 본인 톤 학습 모듈 — 본 도구의 진짜 차별점.

USP: "AI 대본인데 본인이 쓴 것 같음"
다른 도구는 모두 generic AI 톤. 본 도구만 본인 톤 매칭.

흐름:
1. 사용자가 본인이 쓴 대본/게시글/스크립트 3-5개 입력
2. LLM이 톤 특징 추출:
   - 어미 패턴 (~잖아 / ~지 / ~예요)
   - 단어 선택 (격식 / 비격식)
   - 문장 길이 평균
   - 자주 쓰는 감탄사/접속어
   - 이모지 사용 빈도
3. 다음 대본 생성 시 해당 톤 자동 적용

저장: shortform_projects/_voice/profiles.json
사용자별로 다중 프로필 가능 (캐주얼/전문가 등 분리)
"""
import json
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path

import api_keys
import llm


VOICE_DIR = Path("shortform_projects") / "_voice"
PROFILES_PATH = VOICE_DIR / "profiles.json"


def _ensure_dir():
    VOICE_DIR.mkdir(parents=True, exist_ok=True)


def _load_profiles() -> dict:
    if not PROFILES_PATH.exists():
        return {}
    try:
        with open(PROFILES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_profiles(data: dict):
    _ensure_dir()
    with open(PROFILES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── 정량 톤 분석 (LLM 없이 빠르게) ─────────────────────────

ENDINGS_PATTERNS = [
    ("~잖아", r"잖아[\.!?]?$|잖아요[\.!?]?$"),
    ("~지", r"지[\.!?]?$"),
    ("~야", r"야[\.!?]?$|이야[\.!?]?$"),
    ("~네", r"네[\.!?]?$|네요[\.!?]?$"),
    ("~데", r"데[\.!?]?$|데요[\.!?]?$"),
    ("~예요/이에요", r"(예요|이에요)[\.!?]?$"),
    ("~합니다", r"합니다[\.!?]?$|입니다[\.!?]?$"),
]


def analyze_tone_quantitative(samples: list) -> dict:
    """LLM 없이 정량 분석 (빠름, 무료).

    Args:
        samples: 사용자의 본인 글 리스트 (각 1-3문장)

    Returns: {
        "avg_sentence_len": float,
        "avg_chars_per_sentence": float,
        "ending_distribution": {ending_label: count, ...},
        "emoji_count_avg": float,
        "exclamation_ratio": float,  # 감탄문 비율
        "question_ratio": float,
        "total_samples": int,
    }
    """
    if not samples:
        return {"total_samples": 0}

    sentence_lens = []
    char_counts = []
    ending_counts: dict = {label: 0 for label, _ in ENDINGS_PATTERNS}
    emoji_counts = []
    exclamations = 0
    questions = 0
    total_sentences = 0

    emoji_re = re.compile(r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF]")

    for text in samples:
        # 원본 텍스트의 ! ? 카운트 (split 전)
        exclamations += text.count("!")
        questions += text.count("?")
        sentences = [s.strip() for s in re.split(r"[.!?。\n]+", text) if s.strip()]
        for s in sentences:
            total_sentences += 1
            sentence_lens.append(len(s.split()))
            char_counts.append(len(s))
            for label, pat in ENDINGS_PATTERNS:
                if re.search(pat, s):
                    ending_counts[label] += 1
                    break
        emoji_counts.append(len(emoji_re.findall(text)))

    if total_sentences == 0:
        return {"total_samples": 0}

    return {
        "total_samples": len(samples),
        "total_sentences": total_sentences,
        "avg_sentence_len_words": round(statistics.mean(sentence_lens), 1) if sentence_lens else 0,
        "avg_chars_per_sentence": round(statistics.mean(char_counts), 1) if char_counts else 0,
        "ending_distribution": ending_counts,
        "dominant_ending": max(ending_counts.items(), key=lambda x: x[1])[0]
                            if any(ending_counts.values()) else "(없음)",
        "emoji_avg_per_sample": round(statistics.mean(emoji_counts), 2) if emoji_counts else 0,
        "exclamation_ratio": round(exclamations / total_sentences, 2),
        "question_ratio": round(questions / total_sentences, 2),
    }


def extract_voice_profile_llm(samples: list) -> dict:
    """LLM으로 더 깊은 톤 분석.

    Returns: {
        "tone_summary": str,       # 한 문장 톤 요약
        "characteristic_phrases": list,  # 자주 쓰는 표현
        "voice_persona": str,      # 페르소나 (예: "친한 누나 톤")
        "do_use": list,            # 자주 쓰는 단어
        "avoid": list,             # 안 쓰는 표현
    }
    """
    if not samples or not api_keys.get_api_key("ANTHROPIC_API_KEY"):
        return {"tone_summary": "(API 필요)", "characteristic_phrases": [],
                "voice_persona": "", "do_use": [], "avoid": []}

    joined = "\n---\n".join(s.strip() for s in samples if s.strip())
    sys_prompt = """당신은 작가의 글쓰기 톤을 분석하는 언어학 전문가입니다.
주어진 글 샘플들에서 작가의 고유한 톤·표현·페르소나를 추출하세요.
JSON으로만 답하세요. 마크다운 코드블록 금지."""

    user_msg = f"""다음은 한 사람이 쓴 글 샘플들입니다. 이 사람의 글쓰기 톤을 분석하세요.

[샘플들]
{joined[:2000]}

다음 형식 (JSON만):
{{
  "tone_summary": "한 문장으로 톤 요약 (예: '친근한 반말, 자주 의문문, 이모지 적당)",
  "characteristic_phrases": ["자주 쓰는 표현 5개"],
  "voice_persona": "이 사람의 글쓰기 페르소나 (예: '20대 후반 여성, 자취 5년차, 솔직한 톤')",
  "do_use": ["자주 쓰는 단어/문장 시작 5개"],
  "avoid": ["이 사람이 안 쓰는 표현 (격식체/딱딱한 광고 카피 등) 3개"]
}}"""

    response = llm.call_claude(sys_prompt, user_msg, prompt_type="voice_extract",
                                max_tokens=600)
    if not response:
        return {"tone_summary": "(분석 실패)", "characteristic_phrases": [],
                "voice_persona": "", "do_use": [], "avoid": []}

    m = re.search(r"\{[\s\S]*\}", response)
    if not m:
        return {"tone_summary": "(JSON 파싱 실패)", "characteristic_phrases": [],
                "voice_persona": "", "do_use": [], "avoid": []}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"tone_summary": "(디코드 실패)", "characteristic_phrases": [],
                "voice_persona": "", "do_use": [], "avoid": []}


def save_profile(user_id: str, profile_name: str, samples: list) -> dict:
    """사용자 톤 프로필 저장.

    Args:
        user_id: 사용자 식별
        profile_name: 프로필 이름 (예: "메인", "리뷰톤")
        samples: 본인 글 샘플들

    Returns: {"ok": bool, "quantitative": dict, "qualitative": dict}
    """
    if not user_id or not profile_name or not samples:
        return {"ok": False, "error": "user_id/profile_name/samples 모두 필요"}

    quant = analyze_tone_quantitative(samples)
    qual = extract_voice_profile_llm(samples)

    profiles = _load_profiles()
    profiles.setdefault(user_id, {})[profile_name] = {
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "samples_count": len(samples),
        "quantitative": quant,
        "qualitative": qual,
        "samples_preview": [s[:80] for s in samples[:3]],
    }
    _save_profiles(profiles)
    return {"ok": True, "quantitative": quant, "qualitative": qual, "error": ""}


def get_profile(user_id: str, profile_name: str = "메인") -> dict:
    """저장된 프로필 가져오기."""
    profiles = _load_profiles()
    return profiles.get(user_id, {}).get(profile_name, {})


def list_profiles(user_id: str) -> list:
    """사용자의 모든 프로필 이름."""
    return list(_load_profiles().get(user_id, {}).keys())


def format_voice_hint(user_id: str, profile_name: str = "메인") -> str:
    """대본 생성 프롬프트에 주입할 톤 가이드.

    빈 문자열 반환 시 톤 매칭 비활성화.
    """
    profile = get_profile(user_id, profile_name)
    if not profile:
        return ""

    quant = profile.get("quantitative", {})
    qual = profile.get("qualitative", {})

    lines = ["[본인 톤 매칭 — 이 사람의 글쓰기 톤으로 작성]"]
    if qual.get("tone_summary"):
        lines.append(f"- 톤 요약: {qual['tone_summary']}")
    if qual.get("voice_persona"):
        lines.append(f"- 페르소나: {qual['voice_persona']}")
    if quant.get("dominant_ending"):
        lines.append(f"- 자주 쓰는 어미: {quant['dominant_ending']}")
    if qual.get("characteristic_phrases"):
        phrases = ", ".join(qual["characteristic_phrases"][:3])
        lines.append(f"- 자주 쓰는 표현: {phrases}")
    if qual.get("avoid"):
        avoid = ", ".join(qual["avoid"][:3])
        lines.append(f"- 피해야 할 표현: {avoid}")
    return "\n".join(lines)
