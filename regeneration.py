"""수익률 기반 자동 재생성 모듈 (Phase 1-C).

핵심 가설:
영상이 게시 후 24시간 내 클릭 0회 → Hook이 약한 것.
같은 상품, 같은 스크립트로 다시 만들어도 결과는 같다.
대신 Hook만 다른 패턴으로 바꿔서 재생성하면 클릭률 회복 가능.

사용 흐름:
1. 사용자가 추적 대시보드에서 manual_clicks를 입력
2. find_underperforming()으로 저성과 영상 자동 식별
3. UI가 "재생성 추천" 배지 표시
4. 사용자가 클릭하면 make_regeneration_prompt()로 새 Hook 제안 프롬프트 생성
5. 재생성 결과는 record_regeneration()으로 기록 (A/B 비교용)

Why 해자:
"왜 안 되는지 알려주는 도구는 없다." 다른 도구는 영상 만들고 끝.
우리는 안 된 영상을 자동으로 진단하고 다른 패턴을 제안한다.
"""
from datetime import datetime, timezone, timedelta


HOOK_PATTERNS = [
    # (id, label, prompt_hint)
    ("question",   "질문 던지기",      "시청자가 답을 알고 싶어지는 호기심 자극 질문"),
    ("shock",      "충격 사실",        "수치/통계로 의외의 사실 제시 (예: '95%가 이걸 모릅니다')"),
    ("problem",    "문제 공감",        "타겟이 겪는 불편함을 한 문장으로 정확히 짚기"),
    ("contrarian", "통념 뒤집기",      "널리 알려진 상식을 반박하는 첫 마디"),
    ("benefit",    "결과 먼저",        "최종 효과를 1초 안에 보여주기 (Before→After 역순)"),
    ("story",      "1초 미니 스토리",  "구체적 인물/상황으로 시작 (예: '제 친구는...')"),
    ("urgency",    "지금 아니면",      "시간/희소성 압박 (단, 거짓 정보 금지)"),
]


def is_underperforming(record: dict, hours: int = 24, max_clicks: int = 0) -> bool:
    """레코드가 저성과인지 판단.

    조건: created_at으로부터 hours 경과 AND manual_clicks <= max_clicks.
    아직 hours 안 지났으면 False (판단 보류).
    """
    created = record.get("created_at", "")
    if not created:
        return False
    try:
        dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - dt
    if age < timedelta(hours=hours):
        return False
    return int(record.get("manual_clicks", 0) or 0) <= max_clicks


def find_underperforming(records: list, hours: int = 24, max_clicks: int = 0) -> list:
    """저성과 레코드만 필터링."""
    return [r for r in records if is_underperforming(r, hours, max_clicks)]


def suggest_alternative_hook(current_hook_type: str) -> dict:
    """현재 Hook 타입을 제외한 다른 패턴 1개 추천 (라운드 로빈)."""
    others = [p for p in HOOK_PATTERNS if p[0] != current_hook_type]
    if not others:
        others = HOOK_PATTERNS
    pick = others[hash(current_hook_type) % len(others)]
    return {"id": pick[0], "label": pick[1], "hint": pick[2]}


def make_regeneration_prompt(record: dict, original_script: str = "") -> str:
    """LLM에 보낼 재생성 프롬프트.

    원본 Hook과 추천 패턴을 함께 알려주고 새 Hook 5개 변형을 요청.
    """
    title = record.get("title", "(제목 미상)")
    original_hook_type = record.get("hook_type", "unknown")
    alt = suggest_alternative_hook(original_hook_type)
    age_hours = _age_hours(record.get("created_at", ""))
    age_str = f"{age_hours}시간 전" if age_hours is not None else "최근"

    return (
        f"이 영상이 게시 후 {age_str}에도 클릭 0회로 저조합니다.\n"
        f"제목: {title}\n"
        f"원본 Hook 타입: {original_hook_type or '미상'}\n\n"
        f"이번에는 '{alt['label']}' 패턴으로 새 Hook 3개를 만드세요.\n"
        f"패턴 가이드: {alt['hint']}\n\n"
        f"각 Hook은 첫 1.5초 안에 끝나는 12자 이내 한국어 한 문장.\n"
        f"규칙: 거짓·과장 금지, 시청자에게 즉시 가치/호기심 제공, 의문문/단정문 혼용.\n\n"
        + (f"참고할 원본 스크립트:\n{original_script[:600]}\n\n" if original_script else "")
        + "출력 형식 (JSON 외 다른 글자 금지):\n"
        + '{"hooks": ["...", "...", "..."]}'
    )


def make_regeneration_record(original_video_id: str, new_video_id: str,
                              reason: str = "low_clicks") -> dict:
    """재생성 이력 1건. project_store에 별도 리스트로 저장 (A/B 비교용)."""
    return {
        "original_video_id": original_video_id,
        "new_video_id": new_video_id,
        "reason": reason,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _age_hours(iso: str):
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - dt
    return int(delta.total_seconds() // 3600)
