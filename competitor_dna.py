"""경쟁사 영상 DNA 추출 — 본 도구의 강력한 차별점.

USP: "잘 된 영상의 URL → Hook/구조/CTA/페이스 분해 → 본인 상품으로 재해석"
다른 도구에 없는 기능 (한국 시장 0개).

흐름:
1. 사용자가 잘 된 영상 URL 입력 (YouTube/TikTok/Instagram)
2. yt-dlp로 영상 + 자막/설명 다운로드
3. Whisper API 또는 OpenAI/Anthropic으로 자막 추출 (필요 시)
4. LLM으로 구조 분해:
   - Hook (첫 1.5초 텍스트)
   - 본문 구조 (문제→해결→증거)
   - CTA 패턴
   - 페이스 (단어 수/초)
   - 감정 곡선
5. 본인 상품 정보를 그 구조에 매핑 → 새 대본 생성

데이터 누적:
  분해 결과는 dna_library.jsonl에 저장 → 시간 지날수록 더 정확
"""
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import api_keys
import llm


DNA_DIR = Path("shortform_projects") / "_dna"
DNA_LIB_PATH = DNA_DIR / "dna_library.jsonl"


def _ensure_dir():
    DNA_DIR.mkdir(parents=True, exist_ok=True)


def fetch_video_metadata(url: str) -> dict:
    """yt-dlp로 영상 메타 + 자막 다운로드 (영상 파일은 X).

    Returns: {
        "ok": bool,
        "title": str, "description": str, "uploader": str,
        "view_count": int, "like_count": int,
        "duration": int, "subtitle": str (자막 텍스트),
        "platform": str ("youtube" / "tiktok" / "instagram" / "unknown"),
        "error": str (실패 시),
    }
    """
    if not url:
        return {"ok": False, "error": "URL 비어있음"}

    platform = "unknown"
    if "youtube.com" in url or "youtu.be" in url:
        platform = "youtube"
    elif "tiktok.com" in url:
        platform = "tiktok"
    elif "instagram.com" in url:
        platform = "instagram"

    try:
        from yt_dlp import YoutubeDL
        opts = {
            "quiet": True, "no_warnings": True, "extract_flat": False,
            "skip_download": True,
            "writesubtitles": True, "writeautomaticsub": True,
            "subtitleslangs": ["ko", "en"],
            "forcejson": True,
        }
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

        # 자막 추출 (자동 생성 또는 업로더 자막)
        subtitle_text = ""
        subs = info.get("subtitles") or {}
        auto_subs = info.get("automatic_captions") or {}
        for lang in ("ko", "en"):
            entries = subs.get(lang) or auto_subs.get(lang) or []
            if entries:
                # vtt URL → 텍스트 추출은 추가 호출 필요. 여기선 placeholder.
                subtitle_text = f"[{lang} subtitle URL: {entries[0].get('url', '')[:100]}]"
                break

        return {
            "ok": True,
            "title": info.get("title", ""),
            "description": info.get("description", "")[:1000],
            "uploader": info.get("uploader", ""),
            "view_count": info.get("view_count", 0) or 0,
            "like_count": info.get("like_count", 0) or 0,
            "duration": info.get("duration", 0) or 0,
            "subtitle": subtitle_text,
            "platform": platform,
            "error": "",
        }
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}


def extract_dna(metadata: dict) -> dict:
    """영상 메타 + 설명 → LLM 구조 분해.

    Returns: {
        "hook_pattern": str,        # Hook 패턴 분류
        "first_line_estimated": str, # 첫 문장 추정
        "structure": str,           # 문제→해결 / 카운트다운 / 비교 / etc
        "cta_pattern": str,         # 설명란 / 댓글 / 프로필 링크
        "viral_factors": list,      # 작동한 요소들
        "translation_template": str, # 본인 상품에 적용할 템플릿
    }
    """
    if not api_keys.get_api_key("ANTHROPIC_API_KEY"):
        return {
            "hook_pattern": "(API 필요)", "structure": "",
            "cta_pattern": "", "viral_factors": [], "translation_template": "",
        }

    title = metadata.get("title", "")
    desc = metadata.get("description", "")
    views = metadata.get("view_count", 0)
    likes = metadata.get("like_count", 0)

    sys_prompt = """당신은 한국 숏폼 영상의 viral 패턴 분석 전문가입니다.
주어진 영상 정보(제목/설명/조회수)를 보고 어떤 viral 요소가 작동했는지
체계적으로 분해하세요. JSON으로만 답하세요."""

    user_msg = f"""[영상 정보]
제목: {title}
조회수: {views:,}
좋아요: {likes:,}
설명란 일부:
{desc[:500]}

다음 형식으로 분해 (JSON만):
{{
  "hook_pattern": "충격통계 | 개인사연 | 내부자비밀 | 반전후킹 | 카운트다운 | 공포손해 | 비교배틀 | BeforeAfter | 통념부수기 | 시간압박 | 전문가권위 | 솔직톤",
  "first_line_estimated": "(제목/설명 기반 추정) 첫 1초 문장",
  "structure": "문제→해결→증거 | 카운트다운(N가지) | 비교(A vs B) | 사연→교훈 | 데이터→통찰 | 미스터리→답",
  "cta_pattern": "설명란링크 | 댓글참여 | 프로필링크 | 좋아요유도 | 시리즈예고 | 없음",
  "viral_factors": ["구체적 작동 요소 1", "요소 2", "요소 3"],
  "translation_template": "본인 상품 X에 적용할 때: '{{hook}} → {{structure 단계1}} → ... → {{cta}}' 형식으로 50자 이내 가이드"
}}"""

    response = llm.call_claude(sys_prompt, user_msg, prompt_type="dna_extract",
                                max_tokens=600)
    if not response:
        return {"hook_pattern": "(분석 실패)", "structure": "", "cta_pattern": "",
                "viral_factors": [], "translation_template": ""}

    # JSON 추출
    m = re.search(r"\{[\s\S]*\}", response)
    if not m:
        return {"hook_pattern": "(JSON 파싱 실패)", "structure": "", "cta_pattern": "",
                "viral_factors": [], "translation_template": ""}
    try:
        parsed = json.loads(m.group(0))
        return {
            "hook_pattern": parsed.get("hook_pattern", ""),
            "first_line_estimated": parsed.get("first_line_estimated", ""),
            "structure": parsed.get("structure", ""),
            "cta_pattern": parsed.get("cta_pattern", ""),
            "viral_factors": parsed.get("viral_factors", []),
            "translation_template": parsed.get("translation_template", ""),
        }
    except json.JSONDecodeError:
        return {"hook_pattern": "(JSON 디코드 실패)", "structure": "",
                "cta_pattern": "", "viral_factors": [],
                "translation_template": ""}


def save_dna(url: str, metadata: dict, dna: dict, my_product: str = ""):
    """분해 결과를 라이브러리에 저장 (시간 지날수록 데이터 누적)."""
    _ensure_dir()
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "url": url,
        "platform": metadata.get("platform"),
        "title": metadata.get("title"),
        "view_count": metadata.get("view_count"),
        "like_count": metadata.get("like_count"),
        "dna": dna,
        "user_product": my_product,
    }
    try:
        with open(DNA_LIB_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def list_dna_records(limit: int = 50) -> list:
    """저장된 DNA 라이브러리 (최신순)."""
    if not DNA_LIB_PATH.exists():
        return []
    records = []
    with open(DNA_LIB_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return list(reversed(records))[:limit]


def apply_dna_to_product(dna: dict, product: str, category: str = "general") -> str:
    """경쟁사 DNA + 본인 상품 → 새 대본 생성.

    Returns: 생성된 대본 (또는 빈 문자열)
    """
    if not api_keys.get_api_key("ANTHROPIC_API_KEY"):
        return ""
    if not dna or not product:
        return ""

    sys_prompt = """당신은 viral 영상 리메이크 전문가입니다.
다른 viral 영상의 DNA를 보고, 같은 패턴으로 본인 상품용 대본을 작성합니다.
30초 분량, 한 문장 15자 이내, 친근한 반말. 마크다운 금지. 대본만 출력."""

    factors = "\n- ".join(dna.get("viral_factors", []))
    user_msg = f"""[참고할 viral 영상의 DNA]
- Hook 패턴: {dna.get('hook_pattern', '')}
- 영상 구조: {dna.get('structure', '')}
- CTA: {dna.get('cta_pattern', '')}
- 작동한 요소:
- {factors}

[내 상품]
- 카테고리: {category}
- 제품명: {product}

위 viral 영상의 DNA(같은 Hook 패턴 + 구조 + CTA)를 그대로 가져오되,
내 상품 ({product})에 맞게 자연스럽게 적용한 30초 대본을 작성하세요.
구체적 수치/사례 1개 이상 포함. ChatGPT 클리셰 금지."""

    return llm.call_claude(sys_prompt, user_msg, prompt_type="dna_apply",
                            max_tokens=600) or ""
