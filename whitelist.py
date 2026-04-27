"""화이트리스트 + 초대 코드 시스템.

본 도구의 가격 정책:
  - Founder (you): 영구 무료 + 모든 기능
  - Founder가 발급한 초대 코드 사용자: 영구 무료 + Pro 기능
  - 일반 사용자: Free (제한) + Pro (유료)

설계:
  - secrets.toml의 FOUNDER_USER_IDS = "id1,id2" 또는 환경변수
  - shortform_projects/_whitelist.json — 초대 코드 + 사용자 매핑
  - is_pro_user(user_id) → bool: founder + invitee + paid 모두 True
  - generate_invite_code(): founder가 호출 (CLI 또는 UI)
  - redeem_invite_code(code, user_id): 사용자가 코드로 등록
"""
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import api_keys


WHITELIST_PATH = os.path.join("shortform_projects", "_whitelist.json")


def _ensure_dir():
    Path(os.path.dirname(WHITELIST_PATH)).mkdir(parents=True, exist_ok=True)


def _load() -> dict:
    if not os.path.exists(WHITELIST_PATH):
        return {"invitees": {}, "invite_codes": {}}
    try:
        with open(WHITELIST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"invitees": {}, "invite_codes": {}}


def _save(data: dict):
    _ensure_dir()
    with open(WHITELIST_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_founder_ids() -> set:
    """secrets/env에서 founder user_id 목록 가져오기.

    설정 위치:
      .streamlit/secrets.toml: FOUNDER_USER_IDS = "you@email.com,partner@email.com"
      또는 환경변수: FOUNDER_USER_IDS=you@email.com,partner@email.com
    """
    raw = api_keys.get_api_key("FOUNDER_USER_IDS") or os.getenv("FOUNDER_USER_IDS", "")
    if not raw:
        return set()
    return {x.strip() for x in raw.split(",") if x.strip()}


def is_founder(user_id: str) -> bool:
    """user_id가 founder인가."""
    if not user_id:
        return False
    return user_id in get_founder_ids()


def is_invitee(user_id: str) -> bool:
    """초대 코드로 등록한 사용자인가."""
    if not user_id:
        return False
    data = _load()
    return user_id in data.get("invitees", {})


def is_pro_user(user_id: str, paid_pro_ids: Optional[set] = None) -> bool:
    """모든 무료/유료 자격 통합 — Pro 기능 사용 가능 여부.

    조건:
      - founder (영구 무료 모든 기능)
      - invitee (founder가 초대한 사용자)
      - paid_pro_ids (결제한 Pro 사용자, 외부에서 주입)
    """
    if not user_id:
        return False
    if is_founder(user_id):
        return True
    if is_invitee(user_id):
        return True
    if paid_pro_ids and user_id in paid_pro_ids:
        return True
    return False


def user_tier(user_id: str, paid_pro_ids: Optional[set] = None) -> str:
    """사용자 티어 라벨 (UI 표시용).

    Returns: "founder" | "invitee" | "pro" | "free"
    """
    if is_founder(user_id):
        return "founder"
    if is_invitee(user_id):
        return "invitee"
    if paid_pro_ids and user_id in paid_pro_ids:
        return "pro"
    return "free"


def generate_invite_code(created_by: str = "", note: str = "",
                          max_uses: int = 1) -> str:
    """새 초대 코드 발급 (founder만 호출).

    Args:
        created_by: 누가 발급했는지 (기록용)
        note: 메모 (예: "베타 사용자 김XX")
        max_uses: 최대 사용 횟수 (기본 1회 — 1명만 등록 가능)

    Returns: 발급된 코드 (예: "INV-A3F9-K2P1")
    """
    code = "INV-" + secrets.token_hex(2).upper() + "-" + secrets.token_hex(2).upper()
    data = _load()
    data.setdefault("invite_codes", {})[code] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": created_by or "founder",
        "note": note,
        "max_uses": int(max_uses),
        "used_by": [],
    }
    _save(data)
    return code


def redeem_invite_code(code: str, user_id: str) -> dict:
    """사용자가 초대 코드 입력 → 화이트리스트 등록.

    Returns:
        {"ok": bool, "reason": str}
    """
    if not code or not user_id:
        return {"ok": False, "reason": "코드와 user_id가 모두 필요합니다"}
    data = _load()
    codes = data.setdefault("invite_codes", {})
    code_info = codes.get(code)
    if not code_info:
        return {"ok": False, "reason": "유효하지 않은 코드"}
    used_by = code_info.get("used_by", [])
    if user_id in used_by:
        return {"ok": False, "reason": "이미 등록된 사용자"}
    if len(used_by) >= int(code_info.get("max_uses", 1)):
        return {"ok": False, "reason": "코드 사용 횟수 초과"}

    used_by.append(user_id)
    code_info["used_by"] = used_by
    data.setdefault("invitees", {})[user_id] = {
        "registered_at": datetime.now(timezone.utc).isoformat(),
        "via_code": code,
        "note": code_info.get("note", ""),
    }
    _save(data)
    return {"ok": True, "reason": f"무료 Pro 티어 등록 완료"}


def list_invite_codes() -> list:
    """모든 초대 코드 목록 (founder 대시보드용)."""
    data = _load()
    out = []
    for code, info in data.get("invite_codes", {}).items():
        out.append({
            "code": code,
            "created_at": info.get("created_at", ""),
            "note": info.get("note", ""),
            "max_uses": info.get("max_uses", 1),
            "used_count": len(info.get("used_by", [])),
            "used_by": info.get("used_by", []),
        })
    return sorted(out, key=lambda x: x["created_at"], reverse=True)


def list_invitees() -> list:
    """모든 초대받은 사용자 목록."""
    data = _load()
    return [
        {"user_id": uid, **info}
        for uid, info in data.get("invitees", {}).items()
    ]


def revoke_invitee(user_id: str) -> bool:
    """초대받은 사용자 권한 철회 (founder만)."""
    data = _load()
    if user_id in data.get("invitees", {}):
        del data["invitees"][user_id]
        _save(data)
        return True
    return False


if __name__ == "__main__":
    # CLI: python whitelist.py [generate|list|revoke]
    import sys
    args = sys.argv[1:]
    if not args or args[0] == "list":
        print("=== 초대 코드 ===")
        for c in list_invite_codes():
            print(f"  {c['code']}  사용 {c['used_count']}/{c['max_uses']}  {c['note']}")
        print(f"\n=== 등록된 사용자 ({len(list_invitees())}명) ===")
        for u in list_invitees():
            print(f"  {u['user_id']}  ({u.get('via_code', '')})  {u.get('note', '')}")
    elif args[0] == "generate":
        note = args[1] if len(args) > 1 else ""
        max_uses = int(args[2]) if len(args) > 2 else 1
        code = generate_invite_code(note=note, max_uses=max_uses)
        print(f"발급: {code}  (사용자에게 전달)")
        print(f"등록 방법: 사용자가 앱에서 '초대 코드 입력' → '{code}' 붙여넣기")
    elif args[0] == "revoke":
        if len(args) < 2:
            print("사용법: python whitelist.py revoke <user_id>")
            sys.exit(1)
        ok = revoke_invitee(args[1])
        print(f"철회: {'성공' if ok else '실패 (해당 사용자 없음)'}")
    else:
        print("사용법: python whitelist.py [list | generate [note] [max_uses] | revoke <user_id>]")
