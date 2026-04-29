"""YouTube Shorts 자동 업로드 (Klap 핵심 차별점 모방).

YouTube Data API v3:
  - videos.insert (resource=snippet,status / 영상 + 메타)
  - 무료 한도: 일 10K units (영상 1개 ≈ 1600 units → 일 6개)
  - OAuth 2.0 필수 (사용자별 채널 권한)

설계:
  - 토큰은 사용자별 ~/.shortform/youtube_token.json
  - Streamlit Cloud에서는 임시 OAuth flow (manual code copy)
  - 실패해도 앱 흐름 안 막음 (수동 업로드 fallback)
"""
import json
import os
from pathlib import Path

import api_keys


# Google API 의존성 — lazy import (없어도 다른 기능 동작)
def _check_deps() -> tuple[bool, str]:
    """Google API 라이브러리 설치 여부 확인."""
    try:
        import googleapiclient.discovery  # noqa
        import google_auth_oauthlib.flow  # noqa
        import google.oauth2.credentials  # noqa
        return True, ""
    except ImportError as e:
        return False, (
            f"Google API 라이브러리 미설치. 다음 명령 실행:\n"
            f"  pip install google-api-python-client google-auth-oauthlib\n"
            f"({e})"
        )


SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_DIR = Path.home() / ".shortform"
TOKEN_PATH = TOKEN_DIR / "youtube_token.json"


def _ensure_dir():
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)


def _load_credentials():
    """저장된 OAuth 토큰 로드. 없으면 None."""
    ok, _ = _check_deps()
    if not ok:
        return None
    if not TOKEN_PATH.exists():
        return None
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            _save_credentials(creds)
        return creds if creds and creds.valid else None
    except Exception:
        return None


def _save_credentials(creds):
    _ensure_dir()
    with open(TOKEN_PATH, "w", encoding="utf-8") as f:
        f.write(creds.to_json())


def is_authenticated() -> bool:
    """OAuth 토큰 유효한지 빠르게 체크."""
    return _load_credentials() is not None


def get_auth_url() -> dict:
    """OAuth 인증 URL 생성. 사용자가 클릭 → 코드 받음.

    Returns: {"ok": bool, "auth_url": str, "error": str (실패시)}
    """
    ok, err = _check_deps()
    if not ok:
        return {"ok": False, "auth_url": "", "error": err}

    client_id = api_keys.get_api_key("YOUTUBE_OAUTH_CLIENT_ID")
    client_secret = api_keys.get_api_key("YOUTUBE_OAUTH_CLIENT_SECRET")
    if not client_id or not client_secret:
        return {
            "ok": False, "auth_url": "",
            "error": ("YOUTUBE_OAUTH_CLIENT_ID + YOUTUBE_OAUTH_CLIENT_SECRET 필요. "
                      "Google Cloud Console에서 OAuth 2.0 Client ID 생성 후 "
                      "secrets.toml에 추가.")
        }

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow

        client_config = {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }
        flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
        flow.redirect_uri = "urn:ietf:wg:oauth:2.0:oob"
        auth_url, _ = flow.authorization_url(prompt="consent",
                                              access_type="offline",
                                              include_granted_scopes="true")
        return {"ok": True, "auth_url": auth_url, "error": ""}
    except Exception as e:
        return {"ok": False, "auth_url": "", "error": f"{type(e).__name__}: {str(e)[:200]}"}


def exchange_code(code: str) -> dict:
    """사용자가 복사한 인증 코드 → 토큰 저장."""
    ok, err = _check_deps()
    if not ok:
        return {"ok": False, "error": err}
    client_id = api_keys.get_api_key("YOUTUBE_OAUTH_CLIENT_ID")
    client_secret = api_keys.get_api_key("YOUTUBE_OAUTH_CLIENT_SECRET")
    if not client_id or not client_secret:
        return {"ok": False, "error": "OAuth 키 미설정"}

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow

        client_config = {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }
        flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
        flow.redirect_uri = "urn:ietf:wg:oauth:2.0:oob"
        flow.fetch_token(code=code.strip())
        _save_credentials(flow.credentials)
        return {"ok": True, "error": ""}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}


def upload_short(video_path: str, title: str, description: str = "",
                  tags: list | None = None, privacy: str = "public") -> dict:
    """YouTube Shorts에 영상 업로드.

    Args:
        video_path: 로컬 영상 파일 경로 (mp4)
        title: 제목 (60자 이내 권장, "#shorts" 자동 추가됨)
        description: 설명란 (해시태그 + 추적 링크 포함)
        tags: 태그 리스트
        privacy: "public" / "unlisted" / "private"

    Returns:
        {"ok": True, "video_id": str, "url": str}
        또는 {"ok": False, "error": str}
    """
    ok, err = _check_deps()
    if not ok:
        return {"ok": False, "error": err}

    creds = _load_credentials()
    if not creds:
        return {"ok": False, "error": "OAuth 인증 필요. is_authenticated() 먼저 확인."}

    if not os.path.exists(video_path):
        return {"ok": False, "error": f"영상 파일 없음: {video_path}"}

    # YouTube Shorts 인식 위해 #shorts 자동 추가
    if "#shorts" not in title.lower():
        title = (title[:55] + " #shorts").strip()
    if "#shorts" not in description.lower():
        description = description.strip() + "\n\n#shorts"

    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        youtube = build("youtube", "v3", credentials=creds)
        body = {
            "snippet": {
                "title": title[:100],  # YouTube 한도 100자
                "description": description[:5000],  # YouTube 한도 5000자
                "tags": (tags or [])[:10],
                "categoryId": "22",  # People & Blogs
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False,
            },
        }
        media = MediaFileUpload(video_path, chunksize=-1, resumable=True,
                                  mimetype="video/mp4")
        request = youtube.videos().insert(part="snippet,status",
                                            body=body, media_body=media)
        response = request.execute()
        video_id = response.get("id", "")
        return {
            "ok": True,
            "video_id": video_id,
            "url": f"https://youtube.com/shorts/{video_id}" if video_id else "",
            "error": "",
        }
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}


def revoke_token() -> bool:
    """토큰 삭제 (사용자가 로그아웃 원할 때)."""
    if TOKEN_PATH.exists():
        try:
            TOKEN_PATH.unlink()
            return True
        except Exception:
            pass
    return False
