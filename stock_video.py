"""스톡 영상/유튜브 검색 모듈 (Phase 2 모듈 분리 #3).

- search_pexels: Pexels API (한국어 → 영어 자동 변환)
- download_video: URL → 파일 저장
- search_youtube_shorts: Data API → yt-dlp 폴백

UI 비의존. 외부 호출 실패는 빈 리스트/False 반환.
"""
import requests

import api_keys
import llm


PEXELS_SEARCH = "https://api.pexels.com/videos/search"
YOUTUBE_SEARCH = "https://www.googleapis.com/youtube/v3/search"


def search_pexels(keyword: str, n: int = 12) -> list:
    """Pexels 세로형 영상 검색. API 키 없으면 빈 리스트."""
    key = api_keys.get_api_key("PEXELS_API_KEY")
    if not key:
        return []
    en_keyword = llm.translate_keyword_to_english(keyword)
    try:
        r = requests.get(
            PEXELS_SEARCH,
            headers={"Authorization": key},
            params={"query": en_keyword, "per_page": n, "orientation": "portrait"},
            timeout=10,
        )
        if r.status_code != 200:
            return []
        out = []
        for v in r.json().get("videos", []):
            files = v.get("video_files") or []
            if not files:
                continue
            hd = next((f for f in files if f.get("quality") == "hd"), files[0])
            out.append({
                "id": v["id"],
                "title": f"{keyword} #{v['id']}",
                "thumbnail": v.get("image", ""),
                "duration": f"0:{v['duration']:02d}",
                "dur_sec": v["duration"],
                "author": v["user"]["name"],
                "download_url": hd.get("link", ""),
            })
        return out
    except Exception:
        return []


def download_video(url: str, dest_path: str) -> bool:
    """원격 영상 → 로컬 파일. 성공 시 True."""
    if not url:
        return False
    try:
        r = requests.get(url, stream=True, timeout=30)
        if r.status_code != 200:
            return False
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception:
        return False


def _search_youtube_ytdlp(keyword: str, n: int = 6) -> list:
    """yt-dlp 폴백 (API 키 불필요)."""
    try:
        from yt_dlp import YoutubeDL
        opts = {
            "quiet": True, "no_warnings": True, "extract_flat": True,
            "skip_download": True, "noplaylist": True,
            "default_search": "ytsearch",
        }
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch{int(n)}:{keyword} shorts", download=False)
        results = []
        for item in (info.get("entries") or [])[:n]:
            vid_id = item.get("id", "")
            if not vid_id:
                continue
            thumbs = item.get("thumbnails") or []
            thumb_url = thumbs[-1].get("url", "") if thumbs else f"https://i.ytimg.com/vi/{vid_id}/hqdefault.jpg"
            results.append({
                "id": vid_id,
                "title": item.get("title", ""),
                "thumbnail": thumb_url,
                "channel": item.get("uploader", "") or item.get("channel", ""),
                "url": f"https://youtube.com/shorts/{vid_id}",
            })
        return results
    except Exception:
        return []


def search_youtube_shorts(keyword: str, n: int = 6) -> list:
    """YouTube 숏폼 검색. API 키 있으면 Data API, 없으면 yt-dlp 폴백."""
    key = api_keys.get_api_key("YOUTUBE_API_KEY")
    if not key:
        return _search_youtube_ytdlp(keyword, n=n)
    try:
        r = requests.get(
            YOUTUBE_SEARCH,
            params={
                "key": key, "q": keyword + " #shorts",
                "type": "video", "part": "snippet",
                "maxResults": n, "videoDuration": "short",
                "order": "viewCount",
            },
            timeout=10,
        )
        if r.status_code != 200:
            return _search_youtube_ytdlp(keyword, n=n)
        results = []
        for item in r.json().get("items", []):
            vid_id = item["id"]["videoId"]
            snippet = item["snippet"]
            results.append({
                "id": vid_id,
                "title": snippet.get("title", ""),
                "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
                "channel": snippet.get("channelTitle", ""),
                "url": f"https://youtube.com/shorts/{vid_id}",
            })
        return results
    except Exception:
        return _search_youtube_ytdlp(keyword, n=n)
