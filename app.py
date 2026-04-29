import streamlit as st
import os, json, subprocess, tempfile, time, re, requests, glob as globmod, random
from pathlib import Path
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont
import project_store
import clip_analyzer
import tracking
import category_templates
import regeneration
import eval_metrics
import api_keys
import llm
import stock_video
import constants
import use_cases
import script_judge
import script_prompts
import viral_patterns
import whitelist
import admin_dashboard
import youtube_uploader
import competitor_dna
from constants import (
    TEMPLATES, CATEGORY_HASHTAGS, COMMON_HASHTAGS,
    BGM_CATEGORY_KEYWORDS, PEXELS_CATEGORY_KEYWORDS,
    CTA_LIBRARY, CTA_COMMON,
)

# ── FFmpeg PATH 자동 감지 (Windows 로컬용) ─────────────────────────
_FFMPEG_CANDIDATES = [
    r"C:\ffmpeg\bin",
    r"C:\ffmpeg\ffmpeg-8.0.1-essentials_build\bin",
    r"C:\Program Files\ffmpeg\bin",
]
for _fp in _FFMPEG_CANDIDATES:
    if os.path.isdir(_fp) and _fp not in os.environ.get("PATH", ""):
        os.environ["PATH"] = _fp + os.pathsep + os.environ.get("PATH", "")
        break

# ── 크로스 플랫폼 임시 디렉토리 ──────────────────────────────────────
TMPDIR = tempfile.gettempdir()

def _ensure_dir(name):
    """TMPDIR 하위에 디렉토리 생성 후 Path 반환"""
    p = Path(TMPDIR) / name
    p.mkdir(exist_ok=True)
    return p

def find_korean_font():
    """시스템에서 한글 폰트 경로를 자동 감지 (Nanum 우선)"""
    candidates = [
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf",
        "C:/Windows/Fonts/malgun.ttf",
        "C:/Windows/Fonts/gulim.ttc",
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    found = globmod.glob("/usr/share/fonts/**/*anum*.ttf", recursive=True)
    if found:
        return found[0]
    return None

def get_audio_duration(path):
    """ffprobe로 오디오 파일 길이(초) 반환"""
    try:
        res = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=10
        )
        return float(json.loads(res.stdout)["format"]["duration"])
    except:
        return 0

def generate_silent_audio(duration_sec, output_path):
    """FFmpeg로 무음 mp3 생성 (데모 모드용)"""
    try:
        r = subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo",
            "-t", str(duration_sec), "-c:a", "libmp3lame", "-b:a", "128k",
            str(output_path)
        ], capture_output=True, text=True, timeout=30)
        return r.returncode == 0 and os.path.exists(output_path)
    except:
        return False


# ── TTS 엔진 함수 ─────────────────────────────────────────────────
def generate_tts_clova(text, output_path, speaker="nara", speed=0):
    """네이버 클로바 TTS API 호출. 성공 시 True."""
    clova_id = os.environ.get("CLOVA_TTS_CLIENT_ID", "")
    clova_sec = os.environ.get("CLOVA_TTS_CLIENT_SECRET", "")
    if not clova_id or not clova_sec:
        return False
    try:
        resp = requests.post(
            "https://naveropenapi.apigw.ntruss.com/tts-premium/v1/tts",
            headers={"X-NCP-APIGW-API-KEY-ID": clova_id,
                     "X-NCP-APIGW-API-KEY": clova_sec,
                     "Content-Type": "application/x-www-form-urlencoded"},
            data={"speaker": speaker, "text": text, "speed": str(speed), "format": "mp3"},
            timeout=30
        )
        if resp.status_code == 200:
            with open(output_path, "wb") as f:
                f.write(resp.content)
            return True
    except:
        pass
    return False


def generate_tts_elevenlabs(text, output_path, voice_id="21m00Tcm4TlvDq8ikWAM", speed=1.0):
    """ElevenLabs TTS API 호출. 성공 시 True."""
    el_key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not el_key:
        return False
    try:
        resp = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={"xi-api-key": el_key, "Content-Type": "application/json"},
            json={"text": text, "model_id": "eleven_multilingual_v2",
                  "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
                  "speed": speed},
            timeout=60
        )
        if resp.status_code == 200:
            with open(output_path, "wb") as f:
                f.write(resp.content)
            return True
    except:
        pass
    return False


def generate_tts_edge(text, output_path, voice="ko-KR-SunHiNeural", speed=1.0):
    """Microsoft Edge TTS (무료, API 키 불필요). 성공 시 True.
    voice 예: ko-KR-SunHiNeural(여성), ko-KR-InJoonNeural(남성), ko-KR-HyunsuMultilingualNeural"""
    try:
        import asyncio, edge_tts
        rate_pct = int((speed - 1.0) * 100)
        rate_str = f"{'+' if rate_pct >= 0 else ''}{rate_pct}%"
        async def _run():
            comm = edge_tts.Communicate(text, voice, rate=rate_str)
            await comm.save(output_path)
        try:
            asyncio.run(_run())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(_run())
            loop.close()
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0
    except Exception:
        return False


def generate_tts_auto(text, output_path, speaker="nara", voice_id="21m00Tcm4TlvDq8ikWAM", speed=1.0):
    """session_state.tts_engine 기준으로 자동 분기. 성공 시 True.
    엔진 우선순위: 선택 엔진 → edge(무료 폴백) → 나머지 유료 엔진."""
    import streamlit as _st
    engine = _st.session_state.get("tts_engine", "edge")
    if engine == "edge":
        if generate_tts_edge(text, output_path, speed=speed):
            return True
        if generate_tts_elevenlabs(text, output_path, voice_id=voice_id, speed=speed):
            return True
        return generate_tts_clova(text, output_path, speaker=speaker, speed=int((speed - 1) * 5))
    if engine == "elevenlabs":
        if generate_tts_elevenlabs(text, output_path, voice_id=voice_id, speed=speed):
            return True
        if generate_tts_edge(text, output_path, speed=speed):
            return True
        return generate_tts_clova(text, output_path, speaker=speaker, speed=int((speed - 1) * 5))
    if generate_tts_clova(text, output_path, speaker=speaker, speed=int((speed - 1) * 5)):
        return True
    if generate_tts_edge(text, output_path, speed=speed):
        return True
    return generate_tts_elevenlabs(text, output_path, voice_id=voice_id, speed=speed)


def cleanup_hook_temp_files():
    """Hook 생성 임시 파일 정리. 실패해도 앱 크래시 방지."""
    import glob as _g
    patterns = [
        "shortform_hooks/hook_tts_*.mp3",
        "shortform_hooks/merged_tts_*.mp3",
        "shortform_hooks/hook_loop_*.mp4",
        "shortform_hooks/hook_tts_adjusted.*",
        "shortform_hooks/tts_concat.txt",
    ]
    removed = 0
    for pat in patterns:
        for f in _g.glob(pat):
            try:
                os.remove(f)
                removed += 1
            except:
                pass
    return removed


st.set_page_config(page_title="Shorts AI Studio", page_icon="🎬", layout="wide", initial_sidebar_state="expanded")

# ── CSS: Runway/Pika 다크 모드 ─────────────────────────────────────
st.markdown("""
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');

:root{
  --bg: #0A0A0F;
  --bg-elevated: #13131A;
  --surface: #1A1A23;
  --surface-hover: #22222D;
  --border: #2A2A35;
  --border-strong: #3D3D4A;
  --text: #F4F4F8;
  --text-muted: #9CA3AF;
  --text-dim: #6B7280;
  --primary: #FF6B35;
  --primary-glow: #FF8B5B;
  --accent-pink: #FF1493;
  --accent-cyan: #06B6D4;
  --accent-purple: #A855F7;
  --success: #10B981;
  --warning: #F59E0B;
  --error: #EF4444;
}

/* 글로벌 다크 — Runway 스타일 + 큰 폰트 */
html, body, [class*="css"]{
  font-family: 'Pretendard', -apple-system, sans-serif !important;
  background: #0A0A0F !important;
  color: #F4F4F8 !important;
  font-size: 16px !important;  /* 기본 폰트 크기 키움 (이전 14px) */
}
.stApp{ background: #0A0A0F !important; color: #F4F4F8 !important; }
.stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6{ color: #F4F4F8 !important; }
.stApp h1{ font-size: 2rem !important; font-weight: 800 !important; }
.stApp h2{ font-size: 1.5rem !important; font-weight: 700 !important; }
.stApp h3{ font-size: 1.2rem !important; font-weight: 700 !important; }
.stApp h4{ font-size: 1.05rem !important; font-weight: 700 !important; }
.stApp h5{ font-size: 0.95rem !important; font-weight: 600 !important; }
.stApp p, .stApp span, .stApp label{ color: #E5E5EB !important; font-size: 0.95rem !important; }
.stApp p{ line-height: 1.6 !important; }
.stMarkdown, .stMarkdown p{ color: #E5E5EB !important; font-size: 0.95rem !important; }
/* 입력 필드 폰트 */
.stTextInput input, .stTextArea textarea, .stSelectbox > div > div{
  font-size: 0.95rem !important;
}
/* 버튼 폰트 키움 */
.stButton > button{ font-size: 0.95rem !important; padding: 12px 24px !important; }
/* 컨테이너 패딩 — viewport 우선 */
.main .block-container{
  padding-top: 1rem !important;
  padding-bottom: 2rem !important;
  padding-left: 2rem !important;
  padding-right: 2rem !important;
  max-width: 1280px !important;
}
@media (max-width: 768px){
  html, body{ font-size: 15px !important; }
  .main .block-container{ padding: 1rem !important; }
}

/* ═════ 사이드바 — 진짜 검정 + 흰 텍스트 강제 ═════ */
/* specificity 최대화: section[data-testid] + 모든 자손 + !important */
section[data-testid="stSidebar"],
section[data-testid="stSidebar"] > div,
section[data-testid="stSidebar"] > div > div{
  background: #000000 !important;
  background-color: #000000 !important;
  border-right: 1px solid rgba(255,255,255,.1) !important;
}
/* 모든 텍스트 요소 흰색 강제 — specificity 강화 */
section[data-testid="stSidebar"] *,
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3,
section[data-testid="stSidebar"] h4,
section[data-testid="stSidebar"] h5,
section[data-testid="stSidebar"] h6,
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] div,
section[data-testid="stSidebar"] small,
section[data-testid="stSidebar"] strong,
section[data-testid="stSidebar"] em,
section[data-testid="stSidebar"] li,
section[data-testid="stSidebar"] a,
section[data-testid="stSidebar"] .stMarkdown,
section[data-testid="stSidebar"] .stMarkdown *{
  color: #FFFFFF !important;
}
/* 제목 더 굵게 */
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3,
section[data-testid="stSidebar"] h4{
  font-weight: 700 !important;
}
/* caption은 약간 흐리게 (단, 보일 정도로) */
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] *,
section[data-testid="stSidebar"] small{
  color: #C4C4D0 !important;
}
section[data-testid="stSidebar"] hr{
  border-color: rgba(255,255,255,.12) !important;
}
/* 버튼 — 다크 글래스 */
section[data-testid="stSidebar"] .stButton > button{
  background: rgba(255,255,255,.05) !important;
  color: #FFFFFF !important;
  border: 1px solid rgba(255,255,255,.15) !important;
  font-weight: 600 !important;
}
section[data-testid="stSidebar"] .stButton > button *{
  color: #FFFFFF !important;
}
section[data-testid="stSidebar"] .stButton > button:hover{
  background: rgba(255,107,53,.15) !important;
  border-color: rgba(255,107,53,.5) !important;
  color: #FF8B5B !important;
}
section[data-testid="stSidebar"] .stButton > button:hover *{
  color: #FF8B5B !important;
}
section[data-testid="stSidebar"] .stButton > button[kind="primary"]{
  background: linear-gradient(135deg, #FF6B35 0%, #FF1493 100%) !important;
  color: #FFFFFF !important;
  border: none !important;
  box-shadow: 0 4px 14px rgba(255,107,53,.4) !important;
}
section[data-testid="stSidebar"] .stButton > button[kind="primary"] *{
  color: #FFFFFF !important;
}
/* 입력 필드 */
section[data-testid="stSidebar"] .stTextInput input,
section[data-testid="stSidebar"] .stTextArea textarea{
  background: #1A1A1A !important;
  color: #FFFFFF !important;
  border: 1px solid rgba(255,255,255,.2) !important;
}
section[data-testid="stSidebar"] .stTextInput input::placeholder,
section[data-testid="stSidebar"] .stTextArea textarea::placeholder{
  color: #888897 !important;
}
section[data-testid="stSidebar"] .stSelectbox > div > div{
  background: #1A1A1A !important;
  color: #FFFFFF !important;
  border: 1px solid rgba(255,255,255,.2) !important;
}
/* expander */
section[data-testid="stSidebar"] div[data-testid="stExpander"]{
  background: rgba(255,255,255,.03) !important;
  border: 1px solid rgba(255,255,255,.12) !important;
}
section[data-testid="stSidebar"] div[data-testid="stExpander"] summary,
section[data-testid="stSidebar"] div[data-testid="stExpander"] summary *{
  color: #FFFFFF !important;
}
/* radio button */
section[data-testid="stSidebar"] .stRadio label,
section[data-testid="stSidebar"] .stRadio label *{
  color: #FFFFFF !important;
}

/* 입력 필드 다크 */
.stTextArea textarea, .stTextInput input{
  background: #13131A !important;
  border: 1px solid #2A2A35 !important;
  border-radius: 10px !important;
  color: #F4F4F8 !important;
  font-family: 'Pretendard', sans-serif !important;
}
.stTextArea textarea:focus, .stTextInput input:focus{
  border-color: #FF6B35 !important;
  box-shadow: 0 0 0 3px rgba(255,107,53,.15) !important;
  outline: none !important;
}
.stTextArea textarea::placeholder, .stTextInput input::placeholder{ color: #6B7280 !important; }
.stTextArea label, .stTextInput label, .stSelectbox label,
.stSlider label, .stRadio label, .stNumberInput label{ color: #E5E5EB !important; }

.stSelectbox>div>div{
  background: #13131A !important;
  border: 1px solid #2A2A35 !important;
  border-radius: 10px !important;
  color: #F4F4F8 !important;
}
.stSelectbox span{ color: #F4F4F8 !important; }
div[role="listbox"]{ background: #1A1A23 !important; border: 1px solid #2A2A35 !important; }
div[role="listbox"] *{ color: #F4F4F8 !important; }

div[data-testid="stExpander"]{
  background: #13131A !important;
  border: 1px solid #2A2A35 !important;
  border-radius: 12px !important;
}
div[data-testid="stExpander"] summary{ color: #F4F4F8 !important; }
div[data-testid="stExpander"] *{ color: #E5E5EB !important; }

/* 일반 버튼 — 다크 글래스 */
.stButton>button{
  background: rgba(255,255,255,.04) !important;
  color: #F4F4F8 !important;
  border: 1px solid rgba(255,255,255,.1) !important;
  border-radius: 10px !important;
  font-family: 'Pretendard', sans-serif !important;
  font-weight: 600 !important;
  padding: 10px 24px !important;
  font-size: .9rem !important;
  transition: all .2s ease !important;
}
.stButton>button:hover{
  background: rgba(255,255,255,.08) !important;
  border-color: rgba(255,107,53,.4) !important;
  transform: translateY(-1px) !important;
}

/* Primary 버튼 — Pika 네온 그라디언트 (가장 임팩트) */
.stButton>button[kind="primary"]{
  background: linear-gradient(135deg, #FF6B35 0%, #F7931E 50%, #FF1493 100%) !important;
  background-size: 200% 200% !important;
  color: #fff !important;
  border: none !important;
  box-shadow: 0 8px 24px rgba(255,107,53,.35), 0 0 60px rgba(255,20,147,.15) !important;
  font-weight: 700 !important;
  animation: gradient-shift 4s ease infinite;
}
.stButton>button[kind="primary"]:hover{
  transform: translateY(-2px) !important;
  box-shadow: 0 12px 32px rgba(255,107,53,.45), 0 0 80px rgba(255,20,147,.25) !important;
}
@keyframes gradient-shift{
  0%, 100% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
}

.stButton>button:disabled{
  background: rgba(255,255,255,.04) !important;
  color: #4A4A55 !important;
  transform: none !important;
  box-shadow: none !important;
}

/* Secondary */
.stButton>button[kind="secondary"]{
  background: rgba(255,255,255,.03) !important;
  color: #E5E5EB !important;
  border: 1px solid rgba(255,255,255,.1) !important;
}

/* Tabs */
.stTabs [data-baseweb="tab-list"]{
  gap: 4px;
  background: rgba(255,255,255,.03);
  padding: 4px;
  border-radius: 10px;
  border: 1px solid rgba(255,255,255,.06);
}
.stTabs [data-baseweb="tab"]{
  font-family: 'Pretendard', sans-serif !important;
  font-weight: 600 !important;
  color: #9CA3AF !important;
  border-radius: 6px;
}
.stTabs [aria-selected="true"]{
  background: linear-gradient(135deg, rgba(255,107,53,.15) 0%, rgba(255,20,147,.1) 100%) !important;
  color: #FF6B35 !important;
}

/* Radio */
.stRadio div[role="radiogroup"] label span{ color: #E5E5EB !important; }

/* 카드 */
.card{
  background: linear-gradient(135deg, #13131A 0%, #1A1A23 100%);
  border: 1px solid #2A2A35;
  border-radius: 16px;
  padding: 20px 24px;
  margin-bottom: 16px;
  transition: transform .2s ease, border-color .2s ease, box-shadow .2s ease;
}
.card:hover{
  transform: translateY(-2px);
  border-color: rgba(255,107,53,.3);
  box-shadow: 0 12px 32px rgba(0,0,0,.4), 0 0 24px rgba(255,107,53,.08);
}
.card-label{
  font-size: .7rem; font-weight: 700; color: #FF6B35 !important;
  text-transform: uppercase; letter-spacing: 1.5px; margin-bottom: 8px;
}
.card h3, .card h4{ color: #F4F4F8 !important; margin: 0 0 8px; }

/* Badges */
.badge{
  display: inline-block; font-size: .72rem; font-weight: 600;
  padding: 4px 10px; border-radius: 20px;
}
.badge-dark{ background: rgba(255,255,255,.08); color: #E5E5EB !important; }
.badge-blue{ background: rgba(59,130,246,.15); color: #60A5FA !important; }
.badge-green{ background: rgba(16,185,129,.15); color: #34D399 !important; }
.badge-red{ background: rgba(239,68,68,.15); color: #F87171 !important; }
.badge-gray{ background: rgba(255,255,255,.06); color: #9CA3AF !important; }

/* Alert boxes — 다크 */
.info-box{
  background: rgba(59,130,246,.08);
  border: 1px solid rgba(59,130,246,.25);
  border-radius: 10px;
  padding: 12px 16px; font-size: .85rem;
  color: #93C5FD !important; margin: 8px 0;
}
.warn-box{
  background: rgba(245,158,11,.08);
  border: 1px solid rgba(245,158,11,.25);
  border-radius: 10px;
  padding: 12px 16px; font-size: .85rem;
  color: #FCD34D !important; margin: 8px 0;
}
.demo-banner{
  background: rgba(239,68,68,.1);
  border: 1px solid rgba(239,68,68,.3);
  border-radius: 10px;
  padding: 12px 16px; font-size: .85rem;
  color: #F87171 !important; margin: 8px 0;
  font-weight: 600; text-align: center;
}
.copy-box{
  background: #13131A;
  border: 1px solid #2A2A35;
  border-radius: 10px;
  padding: 14px 18px; font-size: .85rem;
  color: #F4F4F8 !important; margin: 8px 0;
  white-space: pre-wrap; word-break: break-all;
  font-family: 'Pretendard', monospace !important;
}
hr{ border-color: rgba(255,255,255,.08) !important; }

/* ux-card 다크 */
.ux-card{
  background: linear-gradient(135deg, #13131A 0%, #1A1A23 100%);
  border: 1px solid #2A2A35;
  border-radius: 16px;
  padding: 24px;
  margin-bottom: 16px;
}
.ux-card-title{
  font-size: .72rem; font-weight: 700;
  color: #FF6B35 !important;
  text-transform: uppercase; letter-spacing: 1.5px; margin-bottom: 6px;
}
.ux-card h4{
  font-size: 1.1rem; font-weight: 700;
  color: #F4F4F8 !important; margin: 0 0 8px;
}
.ux-sub{ color: #9CA3AF !important; font-size: .85rem; }

/* opt-card */
.opt-card{
  background: #13131A;
  border: 1px solid #2A2A35;
  border-radius: 12px;
  padding: 16px 20px;
  height: 100%;
  transition: all .2s ease;
}
.opt-card:hover{
  border-color: rgba(255,107,53,.3);
  background: #1A1A23;
}
.opt-card-icon{ font-size: 1.6rem; margin-bottom: 4px; }
.opt-card-title{ font-size: .9rem; font-weight: 700; color: #F4F4F8 !important; margin: 4px 0; }
.opt-card-desc{ font-size: .78rem; color: #9CA3AF !important; margin-bottom: 8px; }

/* Metric cards */
[data-testid="stMetric"]{
  background: linear-gradient(135deg, #13131A 0%, #1A1A23 100%) !important;
  border: 1px solid #2A2A35;
  border-radius: 12px;
  padding: 14px 18px;
  transition: all .2s ease;
}
[data-testid="stMetric"]:hover{
  transform: translateY(-2px);
  border-color: rgba(255,107,53,.3);
}
[data-testid="stMetricValue"]{
  font-weight: 800 !important; color: #F4F4F8 !important; font-size: 1.6rem !important;
}
[data-testid="stMetricLabel"]{
  color: #9CA3AF !important;
  font-size: .72rem !important; font-weight: 600 !important;
  text-transform: uppercase; letter-spacing: .8px;
}

/* Alerts (st.success/error/warning/info) */
.stAlert{
  border-radius: 12px !important;
  background: rgba(255,255,255,.04) !important;
  border: 1px solid rgba(255,255,255,.08) !important;
}

/* Code blocks */
code{
  background: rgba(255,107,53,.1) !important;
  color: #FF8B5B !important;
  border-radius: 4px !important;
  padding: 2px 6px !important;
}
pre code{ background: #13131A !important; color: #F4F4F8 !important; }

/* Links */
a{ color: #FF6B35 !important; text-decoration: none !important; transition: color .15s; }
a:hover{ color: #FF8B5B !important; text-decoration: underline !important; }

/* 헤더 H1 — Runway 스타일 그라디언트 */
.main h1{
  background: linear-gradient(135deg, #F4F4F8 0%, #FF6B35 60%, #FF1493 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  letter-spacing: -.025em;
  font-weight: 800;
}

/* 진행률 바 */
[data-testid="stProgress"] > div > div > div{
  background: linear-gradient(90deg, #FF6B35 0%, #FF1493 100%) !important;
}

/* 스크롤바 */
::-webkit-scrollbar{ width: 8px; height: 8px; }
::-webkit-scrollbar-track{ background: #0A0A0F; }
::-webkit-scrollbar-thumb{ background: #2A2A35; border-radius: 4px; }
::-webkit-scrollbar-thumb:hover{ background: #3D3D4A; }

/* Pill 배지 */
.pill{
  display: inline-flex; align-items: center; gap: 4px;
  padding: 4px 10px; border-radius: 9999px;
  font-size: .72rem; font-weight: 600;
  background: rgba(255,107,53,.12);
  color: #FF8B5B !important;
  border: 1px solid rgba(255,107,53,.25);
}
.pill-success{ background: rgba(16,185,129,.1); color: #34D399 !important; border-color: rgba(16,185,129,.25); }
.pill-warning{ background: rgba(245,158,11,.1); color: #FCD34D !important; border-color: rgba(245,158,11,.25); }

/* 모바일 반응형 */
@media (max-width:768px){
  .main h1{ font-size: 1.6rem !important; }
  .main .block-container{ padding: 1rem !important; }
  .card, .ux-card{ padding: 16px !important; }
}

/* (라이트 모드 폴리시 제거됨 — 다크 테마 사용) */

/* ═════ AI 영상 SaaS 스타일 — Runway/Pika/Synthesia 패턴 ═════ */

/* Generate 버튼 강조 (✨ 키워드 포함된 primary) */
button[kind="primary"]:has(div p:contains("생성")),
button[kind="primary"]:has(div p:contains("✨")),
button[kind="primary"]:has(div:contains("Generate")){
  background: linear-gradient(135deg, #FF6B35 0%, #F7931E 50%, #FF1493 100%) !important;
  background-size: 200% 200% !important;
  animation: gradient-shift 3s ease infinite;
  box-shadow: 0 8px 24px rgba(255,107,53,.4), 0 0 60px rgba(255,20,147,.15) !important;
  font-size: 1rem !important;
  padding: 14px 28px !important;
  font-weight: 800 !important;
}
@keyframes gradient-shift {
  0%, 100% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
}

/* 영상/대본 결과 카드 (갤러리 스타일) */
.result-card{
  position: relative;
  background: linear-gradient(135deg, #FFFFFF 0%, #FAFBFC 100%);
  border: 1px solid #E5E8EB;
  border-radius: 16px;
  padding: 20px;
  overflow: hidden;
  transition: transform .3s ease, box-shadow .3s ease, border-color .3s ease;
}
.result-card::before{
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, transparent 0%, transparent 50%, rgba(255,107,53,.04) 100%);
  pointer-events: none;
}
.result-card:hover{
  transform: translateY(-4px);
  box-shadow: 0 16px 48px rgba(0,0,0,.1), 0 0 24px rgba(255,107,53,.08);
  border-color: rgba(255,107,53,.3);
}

/* 워크플로우 카드 호버 (큰 STEP 카드) */
.main > div:has(> div > div[style*="linear-gradient(135deg,#FF6B35"]) > div:hover{
  transform: translateY(-2px);
}

/* 사이드바 — 더 깊은 글래스모피즘 */
[data-testid="stSidebar"]{
  background: linear-gradient(180deg, rgba(250,251,252,.95) 0%, rgba(242,244,247,.98) 100%) !important;
  backdrop-filter: blur(20px) saturate(180%);
  border-right: 1px solid rgba(229,232,235,.4) !important;
}

/* 강조 헤더 (h1) — Runway 스타일 그라디언트 */
.main h1{
  background: linear-gradient(135deg, #1A1A2E 0%, #FF6B35 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  letter-spacing: -.02em;
  font-weight: 800;
}

/* 진행 그라디언트 바 (작업 중일 때) */
[data-testid="stProgress"] > div > div > div{
  background: linear-gradient(90deg, #FF6B35 0%, #F7931E 50%, #FF1493 100%) !important;
}

/* 카드 그리드 (CapCut/Synthesia 스타일) */
.video-grid{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
  margin: 16px 0;
}

/* 작은 배지 — pill 스타일 */
.pill{
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: 9999px;
  font-size: .72rem;
  font-weight: 600;
  background: rgba(255,107,53,.1);
  color: #FF6B35;
  border: 1px solid rgba(255,107,53,.2);
}
.pill-success{ background: rgba(16,185,129,.1); color: #10B981; border-color: rgba(16,185,129,.2); }
.pill-warning{ background: rgba(245,158,11,.1); color: #F59E0B; border-color: rgba(245,158,11,.2); }

/* 모바일 폴리시 */
@media (max-width:768px){
  .main h1{font-size:1.6rem !important;}
  .video-grid{grid-template-columns:1fr;gap:12px;}
}
</style>
""", unsafe_allow_html=True)

# ── 상태 초기화 ────────────────────────────────────────────────────
defaults = {
    "clips":[], "clip_order":[], "script":"", "output_path":None,
    "tts_done":False, "subtitle_done":False, "sample_subs":[],
    "script_history":[], "subtitle_history":[], "search_results":[],
    "active_use_case": "coupang_affiliate",
    "user_id": "",  # 사용자 식별 (이메일 또는 익명 ID), whitelist 체크용
    "coupang_product":"", "coupang_category":"", "coupang_titles":[],
    "coupang_script":"", "coupang_hashtags":"", "coupang_desc":"",
    "product_images":[], "uploaded_images":[], "_prod_videos":[], "_yt_results":[], "_ai_trend_result":"",
    "content_mode":"클릭유도형", "coupang_affiliate_link":"",
    "hook_suggestions":[], "selected_hook":"",
    "hashtag_list":[], "hashtag_selections":{},
    "generated_titles":[], "selected_title":"",
    "sub_animation":"없음", "sub_margin":50, "ass_path":"",
    "bgm_results":[], "selected_bgm":"", "bgm_volume":0.2,
    "thumbnail_paths":[],
    "cta_text":"", "cta_position":"하단", "cta_duration":3, "cta_color":"#FFFFFF",
    # ── STEP 네비게이션 ──
    "current_step":1, "source_type":"URL",
    "pexels_searched":False, "pexels_results":[], "youtube_results":[], "instagram_links":[],
    "_last_coupang_url":"", "_last_product":"", "_last_category":"",
    # ── 조회수 최적화 ──
    "hook_test_enabled":False, "hook_version_count":2, "hook_versions":[],
    "pattern_interrupt_enabled":True, "retention_booster_enabled":True,
    # ── TTS 엔진 ──
    "tts_engine":"edge",  # "edge" (free, no key) | "elevenlabs" | "clova"
    # ── 프로젝트 / 템플릿 ──
    "app_phase":"project_select",  # "project_select" | "template_select" | "pipeline"
    "active_project_id":"",
    "active_template":"",
    # ── Multi-Video Generator ──
    "multi_video_enabled":False,
    "multi_video_outputs":[],
    # ── OG 스크래핑 / yt-dlp ──
    "og_tags":{},               # scrape_og_tags 결과
    "pexels_ai_keywords":[],    # Claude AI 추천 Pexels 검색 키워드
    # ── 초보자 UX / Anti-Shadowban ──
    "onboarding_done":False,
    "anti_shadowban_enabled":False,
    "active_preset":"standard",
    # ── 추천 영상 (7차) ──
    "recommended_videos":[],
    "recommended_keywords":[],
    "selected_recommended_video":None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# 템플릿 정의는 constants.py로 추출 (TEMPLATES alias)


# ── 프로젝트 선택 화면 ──────────────────────────────────────────
def render_project_select():
    # ── Hero 섹션 (Runway 다크 스타일) ──
    if not st.session_state.get("onboarding_done", False):
        st.markdown("""
<div class="hero-runway">
  <div class="hero-bg-glow"></div>
  <div class="hero-content">
    <div class="hero-eyebrow">SHORTS AI · STUDIO</div>
    <h1 class="hero-title">
      AI가 만드는 <span class="hero-accent">바이럴 영상</span>
    </h1>
    <p class="hero-subtitle">
      쿠팡 · 부업 · 유튜브 · 브이로그 — 모든 숏폼을 한 곳에서.
    </p>
    <div class="hero-flow">
      <div class="hero-pill">🛒 쿠팡</div>
      <span class="hero-arrow">→</span>
      <div class="hero-pill">🎬 영상</div>
      <span class="hero-arrow">→</span>
      <div class="hero-pill">🤖 AI 대본</div>
      <span class="hero-arrow">→</span>
      <div class="hero-pill">🔗 추적</div>
      <span class="hero-arrow">→</span>
      <div class="hero-pill hero-pill-final">📊 매출</div>
    </div>
  </div>
</div>
<style>
.hero-runway{
  position: relative;
  background: linear-gradient(135deg, #0A0A0F 0%, #1A0F2E 40%, #3D1A4D 80%, #FF1493 110%);
  border-radius: 20px;
  padding: 28px 32px;
  margin: 4px 0 16px;
  overflow: hidden;
  border: 1px solid rgba(255,107,53,.2);
  box-shadow: 0 12px 40px rgba(255,20,147,.18), 0 0 60px rgba(255,107,53,.08);
}
.hero-bg-glow{
  position: absolute;
  top: -40%; right: -20%;
  width: 70%; height: 180%;
  background: radial-gradient(circle, rgba(255,107,53,.25) 0%, rgba(255,20,147,.1) 40%, transparent 70%);
  filter: blur(50px);
  pointer-events: none;
}
.hero-content{ position: relative; z-index: 2; max-width: 720px; }
.hero-eyebrow{
  font-size: .68rem; font-weight: 700;
  color: rgba(255,255,255,.7) !important;
  text-transform: uppercase; letter-spacing: 2px;
  margin-bottom: 8px;
}
.hero-title{
  margin: 0 0 10px !important;
  font-size: 1.9rem !important;
  font-weight: 800 !important;
  color: #FFFFFF !important;
  line-height: 1.15 !important;
  letter-spacing: -.02em !important;
  background: none !important;
  -webkit-text-fill-color: #FFFFFF !important;
}
.hero-accent{
  background: linear-gradient(135deg, #FF6B35 0%, #FFB088 50%, #FF1493 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  display: inline-block;
}
.hero-subtitle{
  font-size: .9rem !important;
  color: rgba(255,255,255,.78) !important;
  margin: 0 0 16px !important;
  line-height: 1.5;
}
.hero-subtitle strong{ color: #FFFFFF !important; }
.hero-flow{
  display: flex; gap: 6px; align-items: center; flex-wrap: wrap;
}
.hero-pill{
  background: rgba(255,255,255,.08);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255,255,255,.15);
  border-radius: 8px;
  padding: 6px 12px;
  font-size: .78rem;
  color: #FFFFFF !important;
  font-weight: 600;
}
.hero-pill-final{
  background: linear-gradient(135deg, rgba(255,107,53,.3) 0%, rgba(255,20,147,.3) 100%);
  border-color: rgba(255,107,53,.5);
  font-weight: 700;
  box-shadow: 0 2px 12px rgba(255,107,53,.25);
}
.hero-arrow{
  color: rgba(255,255,255,.4) !important;
  font-size: .95rem;
}
@media (max-width:768px){
  .hero-runway{ padding: 20px 18px; }
  .hero-title{ font-size: 1.4rem !important; }
  .hero-subtitle{ font-size: .82rem !important; }
}
</style>
""", unsafe_allow_html=True)
        _ob_c = st.columns([1, 2, 1])
        with _ob_c[1]:
            if st.button("✨ 시작하기", type="primary", use_container_width=True, key="onboarding_start"):
                st.session_state.onboarding_done = True
                st.rerun()

    st.markdown('<div class="ux-card"><div class="ux-card-title">HOME</div><h4>📁 프로젝트 선택</h4><p class="ux-sub">프로젝트를 선택하거나 새로 만들어주세요</p></div>', unsafe_allow_html=True)

    # ── 🎫 일반 사용자용 초대 코드 입력 (Free 티어만 노출) ──
    _curr_uid = st.session_state.get("user_id", "")
    _curr_tier = whitelist.user_tier(_curr_uid) if _curr_uid else "free"
    if _curr_uid and _curr_tier == "free":
        with st.expander("🎟️ 초대 코드 등록 (있다면)"):
            _code_input = st.text_input(
                "초대 코드", placeholder="INV-XXXX-XXXX",
                key="_invite_code_input",
            )
            if st.button("등록", key="btn_redeem"):
                _result = whitelist.redeem_invite_code(_code_input.strip(), _curr_uid)
                if _result["ok"]:
                    st.success(f"✅ {_result['reason']}")
                    st.rerun()
                else:
                    st.error(f"❌ {_result['reason']}")

    # 새 프로젝트 생성
    with st.expander("➕ 새 프로젝트 만들기", expanded=not bool(project_store.list_projects())):
        _np_name = st.text_input("프로젝트 이름", placeholder="예: 배수구 냄새 제거기", key="_new_prj_name")

        # ── 🎯 Use Case 선택 (Phase 3 TAM 확장) ──
        _uc_options = use_cases.list_use_cases()
        _uc_labels = [f"{label} — {desc}" for _, label, desc in _uc_options]
        _uc_idx = st.radio(
            "어떤 영상을 만드시나요?",
            range(len(_uc_options)),
            format_func=lambda i: _uc_labels[i],
            key="_new_prj_use_case_idx",
            help="용도에 따라 Hook 패턴, 영상 구조, 성과 지표가 달라집니다.",
        )
        _np_use_case = _uc_options[_uc_idx][0]

        _np_product = st.text_input("제품/주제명 (선택)", placeholder="예: 만능 배수구 클리너 / 강남 카페 투어", key="_new_prj_product")
        _np_cat = st.selectbox("카테고리", ["전자기기", "뷰티/화장품", "패션/의류", "식품", "생활용품", "건강/헬스", "유아/키즈", "반려동물", "기타"], key="_new_prj_cat")
        if st.button("✅ 프로젝트 생성", key="btn_create_prj", type="primary"):
            if _np_name.strip():
                pid = project_store.create_project(_np_name.strip(), product_name=_np_product, category=_np_cat)
                st.session_state.active_project_id = pid
                st.session_state.active_use_case = _np_use_case
                st.session_state.app_phase = "template_select"
                if _np_product:
                    st.session_state.coupang_product = _np_product
                if _np_cat:
                    st.session_state.coupang_category = _np_cat
                st.rerun()
            else:
                st.warning("프로젝트 이름을 입력해주세요")

    # 기존 프로젝트 목록
    projects = project_store.list_projects()
    if projects:
        st.markdown("#### 📋 기존 프로젝트")
        for prj in projects:
            col_info, col_open, col_del = st.columns([4, 1, 1])
            with col_info:
                _tpl = prj.get("template", "")
                _tpl_name = TEMPLATES.get(_tpl, {}).get("name", _tpl) if _tpl else "미선택"
                st.markdown(f"**{prj['name']}**  \n📅 {prj['created_at'][:10]}  ·  🎬 영상 {prj['video_count']}개  ·  📋 {_tpl_name}")
            with col_open:
                if st.button("열기", key=f"open_{prj['id']}", type="primary"):
                    st.session_state.active_project_id = prj['id']
                    pdata = project_store.get_project(prj['id'])
                    if pdata:
                        if pdata.get("product_name"):
                            st.session_state.coupang_product = pdata["product_name"]
                        if pdata.get("category"):
                            st.session_state.coupang_category = pdata["category"]
                        if pdata.get("template"):
                            st.session_state.active_template = pdata["template"]
                            _apply_template(pdata["template"])
                            st.session_state.app_phase = "pipeline"
                            st.session_state.current_step = 1
                        else:
                            st.session_state.app_phase = "template_select"
                    st.rerun()
            with col_del:
                if st.button("🗑️", key=f"del_{prj['id']}"):
                    project_store.delete_project(prj['id'])
                    st.rerun()
    elif not projects:
        st.info("아직 프로젝트가 없습니다. 위에서 새로 만들어주세요!")

    # ── 📊 추적 대시보드 (Phase 1-B 해자: 영상→매출 가시화) ──
    _all_track = project_store.list_all_tracking_records()
    if _all_track:
        st.markdown("---")
        st.markdown("#### 📊 추적 대시보드 — 영상별 매출 귀속")

        # ── API 승인 전/후 안내 ──
        _has_partners_api = has_key("COUPANG_PARTNERS_ACCESS_KEY") and has_key("COUPANG_PARTNERS_SECRET_KEY")
        if not _has_partners_api:
            st.markdown(
                '<div style="background:linear-gradient(135deg,#FFF7ED 0%,#FED7AA 100%);'
                'border:1px solid #FDBA74;border-radius:12px;padding:14px;margin:8px 0;'
                'font-size:.88rem;color:#7C2D12;">'
                '🚧 <strong>쿠팡 파트너스 API 미승인 단계</strong> — 자동 매출 회수 불가.<br>'
                '대안: ① 영상마다 subId 다르게 해서 단축 링크 생성 → '
                '② 7일 후 파트너스 리포트에서 subId별 매출 확인 → '
                '③ <strong>아래 CSV 업로드</strong> 또는 표에 직접 입력.<br>'
                '<span style="opacity:.7;font-size:.82rem;">'
                'API는 매출 발생 + 활동 회원 승인 후 발급됨 (정책)'
                '</span>'
                '</div>',
                unsafe_allow_html=True,
            )

        # ── 📂 CSV 업로드 (파트너스 매출 리포트) ──
        with st.expander("📂 쿠팡 파트너스 CSV 업로드 (매출 자동 매칭)"):
            st.caption("쿠팡 파트너스 → 수익 리포트 → CSV 다운로드 → 여기 업로드 시 subId별 매출 자동 채움")
            _csv_file = st.file_uploader(
                "CSV 파일", type=["csv"], key="_partners_csv_upload",
                label_visibility="collapsed",
            )
            if _csv_file:
                try:
                    _csv_records = tracking.parse_partners_csv(_csv_file.read())
                    if not _csv_records:
                        st.warning("CSV 파싱 실패 — subId 컬럼이 있는지 확인하세요.")
                    else:
                        # subId → 매칭
                        _csv_map = {r["sub_id"]: r for r in _csv_records}
                        _matched = 0
                        for _r in _all_track:
                            _sid = _r.get("sub_id", "")
                            if _sid and _sid in _csv_map:
                                _data = _csv_map[_sid]
                                project_store.update_tracking_metrics(
                                    _r["project_id"], _r["video_id"],
                                    manual_clicks=_data["clicks"],
                                    manual_revenue_krw=_data["revenue_krw"],
                                )
                                _matched += 1
                        st.success(f"✅ {_matched}건 자동 매칭 완료 / 총 {len(_csv_records)}개 CSV 행")
                        if _matched > 0:
                            st.rerun()
                except Exception as e:
                    st.error(f"CSV 처리 오류: {type(e).__name__}")

        _total_clicks = sum(int(r.get("manual_clicks", 0) or 0) for r in _all_track)
        _total_rev = sum(int(r.get("manual_revenue_krw", 0) or 0) for r in _all_track)
        _mc1, _mc2, _mc3 = st.columns(3)
        _mc1.metric("총 영상 수", f"{len(_all_track)}개")
        _mc2.metric("총 클릭", f"{_total_clicks:,}")
        _mc3.metric("총 매출", f"{_total_rev:,}원")

        for _i, _rec in enumerate(reversed(_all_track[-20:])):
            with st.container(border=True):
                _rc1, _rc2, _rc3 = st.columns([3, 2, 2])
                with _rc1:
                    st.markdown(f"**{_rec.get('project_name', '')}** · {_rec.get('title', '')}")
                    st.caption(f"subId: `{_rec.get('sub_id', '')}` · {_rec.get('created_at', '')[:10]}")
                    if _rec.get("shorten_url"):
                        st.caption(f"🔗 {_rec['shorten_url']}")
                with _rc2:
                    _new_clicks = st.number_input(
                        "클릭 수",
                        value=int(_rec.get("manual_clicks", 0) or 0),
                        min_value=0,
                        step=1,
                        key=f"track_clk_{_rec.get('sub_id', _i)}"
                    )
                with _rc3:
                    _new_rev = st.number_input(
                        "매출 (원)",
                        value=int(_rec.get("manual_revenue_krw", 0) or 0),
                        min_value=0,
                        step=1000,
                        key=f"track_rev_{_rec.get('sub_id', _i)}"
                    )
                if (_new_clicks != int(_rec.get("manual_clicks", 0) or 0) or
                    _new_rev != int(_rec.get("manual_revenue_krw", 0) or 0)):
                    if st.button("💾 저장", key=f"track_save_{_rec.get('sub_id', _i)}"):
                        project_store.update_tracking_metrics(
                            _rec["project_id"], _rec["video_id"],
                            manual_clicks=_new_clicks, manual_revenue_krw=_new_rev
                        )
                        st.success("저장됨!")
                        st.rerun()

        # ── 🔁 저성과 영상 자동 감지 (Phase 1-C 수익률 기반 재생성) ──
        _under = regeneration.find_underperforming(_all_track, hours=24, max_clicks=0)
        if _under:
            st.markdown("#### 🔁 재생성 추천 — 24시간 내 클릭 0회")
            st.caption("다른 Hook 패턴으로 재생성하면 클릭률이 회복될 수 있습니다. 같은 스크립트로 다시 만들어도 결과는 같습니다.")
            for _u in _under[:10]:
                _alt = regeneration.suggest_alternative_hook(_u.get("hook_type", ""))
                with st.container(border=True):
                    _uc1, _uc2 = st.columns([3, 2])
                    with _uc1:
                        st.markdown(f"**{_u.get('title', '(제목 미상)')}** · {_u.get('project_name', '')}")
                        st.caption(f"원본 Hook: `{_u.get('hook_type') or '미상'}` → 추천 패턴: **{_alt['label']}**")
                        st.caption(f"가이드: {_alt['hint']}")
                    with _uc2:
                        if st.button("📋 재생성 프롬프트 복사", key=f"regen_{_u.get('sub_id', _u.get('video_id',''))}"):
                            st.session_state["_regen_prompt"] = regeneration.make_regeneration_prompt(_u)
                            st.session_state["_regen_title"] = _u.get("title", "")
            if st.session_state.get("_regen_prompt"):
                with st.expander(f"📝 재생성 프롬프트 — {st.session_state.get('_regen_title','')}"):
                    st.code(st.session_state["_regen_prompt"], language="markdown")
                    st.caption("위 프롬프트를 STEP 2 스크립트 생성에 복사하거나, Claude에 직접 붙여넣어 새 Hook 3개를 받을 수 있습니다.")

    # ── 📊 품질 메트릭 (Phase 1-C 평가) — 추적 레코드와 독립 표시 ──
    with st.expander("📊 품질 메트릭 — LLM 호출 편차 (7일)"):
        _stats = eval_metrics.compute_stats(days=7)
        if _stats["count"] == 0:
            st.caption("아직 LLM 호출 기록이 없습니다. STEP 2/3에서 스크립트를 생성하면 지표가 누적됩니다.")
        else:
            _qc1, _qc2, _qc3 = st.columns(3)
            _qc1.metric("7일 호출 수", _stats["count"])
            _qc2.metric("평균 글자 수", _stats["metrics"]["char_len"]["mean"])
            _qc3.metric("평균 지연", f"{_stats['latency_ms']['mean']}ms")
            st.caption(f"Hook 포함률 {_stats['metrics']['has_hook_pct']}% · CTA 포함률 {_stats['metrics']['has_cta_pct']}% · 글자 표준편차 {_stats['metrics']['char_len']['stdev']}")
            if _stats["by_prompt_type"]:
                st.caption("프롬프트별 호출 수: " + ", ".join(f"{k}={v}" for k, v in _stats["by_prompt_type"].items()))


# ── 템플릿 선택 화면 ──────────────────────────────────────────
def _apply_template(template_key):
    """템플릿 설정을 session_state에 적용."""
    tpl = TEMPLATES.get(template_key)
    if not tpl:
        return
    st.session_state.active_template = template_key
    st.session_state.content_mode = tpl.get("content_mode", "클릭유도형")
    st.session_state.pattern_interrupt_enabled = tpl.get("pattern_interrupt", True)
    st.session_state.retention_booster_enabled = tpl.get("retention_booster", True)
    st.session_state.tts_engine = tpl.get("tts_engine", "edge")
    st.session_state.cta_position = tpl.get("cta_position", "하단")
    # Template 차별화 필드
    if tpl.get("cta_text"):
        st.session_state.cta_text = tpl["cta_text"]
    if tpl.get("sub_color"):
        st.session_state.cta_color = tpl["sub_color"]


def render_template_select():
    st.markdown('<div class="ux-card"><div class="ux-card-title">TEMPLATE</div><h4>📋 템플릿 선택</h4><p class="ux-sub">영상 구조를 선택하면 자동으로 설정됩니다</p></div>', unsafe_allow_html=True)

    # 현재 프로젝트 정보
    pid = st.session_state.active_project_id
    pdata = project_store.get_project(pid) if pid else None
    if pdata:
        st.markdown(f"**프로젝트:** {pdata['name']}")

    cols = st.columns(2)
    tpl_keys = list(TEMPLATES.keys())
    for i, tkey in enumerate(tpl_keys):
        tpl = TEMPLATES[tkey]
        with cols[i % 2]:
            st.markdown(f'<div class="opt-card">', unsafe_allow_html=True)
            st.markdown(f"**{tpl['name']}**")
            st.caption(tpl['desc'])
            _settings = []
            if tpl.get("pattern_interrupt"):
                _settings.append("⚡ PI")
            if tpl.get("retention_booster"):
                _settings.append("📈 RB")
            _settings.append(f"🔊 {tpl.get('tts_engine', 'elevenlabs')}")
            st.markdown(f"설정: {' · '.join(_settings)}")
            if st.button(f"선택 →", key=f"tpl_{tkey}", type="primary"):
                _apply_template(tkey)
                if pid:
                    project_store.update_project(pid, template=tkey)
                st.session_state.app_phase = "pipeline"
                st.session_state.current_step = 1
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("---")
    if st.button("← 프로젝트 목록으로", key="back_to_projects", type="secondary"):
        st.session_state.app_phase = "project_select"
        st.rerun()


# 카테고리별 해시태그/BGM 키워드/Pexels 키워드/CTA 라이브러리는 constants.py로 추출

# (CTA_LIBRARY/CTA_COMMON 원본은 constants.py로 이동)

# ── 헬퍼 함수 (Phase 2 모듈 분리: api_keys/llm/stock_video로 추출, 호환 래퍼) ──
get_api_key = api_keys.get_api_key
has_key = api_keys.has_key


def call_claude(system_prompt, user_msg, max_tokens=1500, prompt_type="generic"):
    """app.py 호환 래퍼 — st.error를 on_error로 주입."""
    return llm.call_claude(
        system_prompt, user_msg, max_tokens=max_tokens, prompt_type=prompt_type,
        on_error=lambda e: st.error(
            f"AI 응답 생성에 실패했습니다. 잠시 후 다시 시도해주세요. ({type(e).__name__})"
        ),
    )


_translate_keyword_to_english = llm.translate_keyword_to_english
search_pexels = stock_video.search_pexels
download_video = stock_video.download_video

search_youtube_shorts = stock_video.search_youtube_shorts

def download_video_ytdlp(url, max_size_mb=100):
    """yt-dlp로 외부 영상 다운로드 (더우인/틱톡/유튜브 등).
    Streamlit Cloud에서는 yt-dlp가 없을 수 있어 fallback 메시지 반환.
    Returns: (file_path, error_message) — 성공 시 (path, None), 실패 시 (None, msg)
    """
    # ── URL 유효성 검사 ──
    url = str(url).strip()
    if not url:
        return None, "URL이 비어있습니다."
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    _blocked = ["google.com/httpservice", "google.com/sorry", "captcha", "recaptcha"]
    if any(b in url.lower() for b in _blocked):
        return None, "Google CAPTCHA/리다이렉트 URL입니다. 원본 영상 URL을 직접 입력하세요."
    _supported_domains = [
        "douyin.com", "tiktok.com", "youtube.com", "youtu.be",
        "instagram.com", "twitter.com", "x.com", "bilibili.com",
        "weibo.com", "xiaohongshu.com", "v.douyin.com",
    ]
    _url_lower = url.lower()
    _domain_ok = any(d in _url_lower for d in _supported_domains)
    if not _domain_ok:
        return None, (
            "⚠️ 지원하지 않는 URL입니다.\n\n"
            "아래 URL 형식만 지원됩니다:\n"
            "✅ https://www.douyin.com/video/xxxxx\n"
            "✅ https://v.douyin.com/xxxxx\n"
            "✅ https://www.tiktok.com/@user/video/xxxxx\n"
            "✅ https://youtube.com/shorts/xxxxx\n"
            "✅ https://www.instagram.com/reel/xxxxx\n"
            "❌ 구글/쿠팡/네이버 등 일반 URL 불가\n\n"
            "직접 다운로드 후 C) 영상 직접 업로드를 이용하세요."
        )

    save_dir = _ensure_dir("ytdlp_downloads")
    # 파일명에 한국어/특수문자(#!() 등) 포함 시 FFmpeg 오류 발생 → ID만 사용
    output_template = str(save_dir / "%(id)s.%(ext)s")
    try:
        # yt-dlp 존재 확인
        check = subprocess.run(["yt-dlp", "--version"], capture_output=True, text=True, timeout=5)
        if check.returncode != 0:
            return None, "yt-dlp가 설치되지 않았습니다. 로컬에서 pip install yt-dlp 후 다시 시도하세요."
    except FileNotFoundError:
        return None, "yt-dlp를 찾을 수 없습니다. Streamlit Cloud에서는 지원되지 않을 수 있어요. 로컬 환경에서 실행해주세요."
    except Exception:
        return None, "yt-dlp 확인 실패"

    try:
        cmd = [
            "yt-dlp",
            "--no-playlist",
            "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "--merge-output-format", "mp4",
            f"--max-filesize", f"{max_size_mb}M",
            "-o", output_template,
            "--no-overwrites",
            "--socket-timeout", "30",
            "--no-check-certificates",
            "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "--extractor-retries", "3",
            str(url),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            err_all = (r.stderr or "") + (r.stdout or "")
            err_msg = err_all[-500:]

            # Google 리다이렉트 감지
            if "google.com" in err_msg.lower() and ("enablejs" in err_msg.lower() or "sorry" in err_msg.lower()):
                return None, (
                    "❌ 네트워크가 Google CAPTCHA로 리다이렉트됩니다.\n\n"
                    "**해결 방법:**\n"
                    "1. 브라우저에서 해당 영상을 먼저 열어 정상 접근 가능한지 확인\n"
                    "2. VPN/프록시를 사용 중이면 해제 후 재시도\n"
                    "3. 원본 영상 URL을 직접 복사하여 붙여넣기\n"
                    "4. 또는 영상을 수동 다운로드 → C) 영상 직접 업로드"
                )
            if "unsupported url" in err_msg.lower():
                return None, f"❌ 지원되지 않는 URL입니다. 더우인/틱톡/유튜브/인스타 등의 영상 URL을 입력하세요.\n\n오류: {err_msg[-200:]}"
            if "max-filesize" in err_msg.lower() or "file is larger" in err_msg.lower():
                return None, f"영상이 {max_size_mb}MB를 초과합니다."
            if "login" in err_msg.lower() or "sign in" in err_msg.lower():
                return None, "❌ 로그인이 필요한 영상입니다. 공개 영상 URL을 사용하세요."
            return None, f"❌ yt-dlp 다운로드 실패:\n{err_msg[-300:]}"

        # 다운로드된 파일 찾기
        downloaded = sorted(save_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
        if downloaded:
            fpath = str(downloaded[0])
            fsize = os.path.getsize(fpath) / (1024 * 1024)
            if fsize > max_size_mb:
                os.remove(fpath)
                return None, f"다운로드된 파일이 {fsize:.0f}MB로 제한({max_size_mb}MB)을 초과합니다."
            return fpath, None
        return None, "다운로드 완료됐지만 파일을 찾을 수 없습니다."
    except subprocess.TimeoutExpired:
        return None, "다운로드 시간 초과 (5분). 더 짧은 영상을 시도하세요."
    except Exception as e:
        return None, f"다운로드 오류: {str(e)[:200]}"


def _download_douyin_scraper(url):
    """douyin-tiktok-scraper 라이브러리로 영상 다운로드 (yt-dlp 실패 시 fallback).
    Returns: (file_path, error_message)
    """
    try:
        from douyin_tiktok_scraper.scraper import Scraper
    except ImportError:
        return None, "douyin-tiktok-scraper 미설치 (pip install douyin-tiktok-scraper)"

    save_dir = _ensure_dir("ytdlp_downloads")
    try:
        import asyncio
        api = Scraper()

        # asyncio 이벤트 루프 처리 (Streamlit에서는 이미 루프가 돌 수 있음)
        try:
            loop = asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = loop.run_in_executor(pool, lambda: asyncio.run(api.hybrid_parsing(url)))
                # Streamlit 환경에서는 직접 실행
                result = asyncio.run(api.hybrid_parsing(url))
        except RuntimeError:
            result = asyncio.run(api.hybrid_parsing(url))

        if not result:
            return None, "douyin-scraper: 파싱 결과 없음"

        # 영상 URL 추출 (nwm_video_url = 워터마크 없는 영상)
        video_url = (
            result.get("nwm_video_url") or
            result.get("nwm_video_url_HQ") or
            result.get("video_url") or
            result.get("download_url", "")
        )
        if not video_url:
            return None, "douyin-scraper: 영상 URL을 찾을 수 없음"

        # 영상 다운로드
        import hashlib
        _hash = hashlib.md5(url.encode()).hexdigest()[:10]
        out_path = str(save_dir / f"ds_{_hash}.mp4")
        resp = requests.get(video_url, timeout=60, stream=True, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        resp.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        if os.path.exists(out_path) and os.path.getsize(out_path) > 10000:
            return out_path, None
        return None, "douyin-scraper: 다운로드된 파일이 너무 작음"
    except Exception as e:
        return None, f"douyin-scraper 오류: {str(e)[:200]}"


def download_video_with_fallback(url, max_size_mb=100):
    """yt-dlp → douyin-tiktok-scraper fallback 순서로 영상 다운로드.
    Returns: (file_path, error_message)
    """
    # 1차: yt-dlp 시도
    fpath, err1 = download_video_ytdlp(url, max_size_mb)
    if fpath:
        return fpath, None

    # URL 유효성 실패인 경우 fallback 불필요 (지원 안 되는 URL)
    if err1 and ("지원하지 않는 URL" in err1 or "비어있습니다" in err1 or "CAPTCHA" in err1):
        return None, err1

    # 2차: douyin/tiktok URL인 경우 douyin-tiktok-scraper fallback
    _url_lower = url.lower()
    if any(d in _url_lower for d in ["douyin.com", "tiktok.com", "v.douyin.com"]):
        fpath2, err2 = _download_douyin_scraper(url)
        if fpath2:
            return fpath2, None
        # 둘 다 실패
        return None, (
            f"❌ 다운로드 실패 (2가지 방법 모두 실패)\n\n"
            f"**yt-dlp 오류:** {err1[:150] if err1 else '알 수 없음'}\n"
            f"**scraper 오류:** {err2[:150] if err2 else '알 수 없음'}\n\n"
            f"💡 영상을 수동 다운로드 후 **C) 영상 직접 업로드**를 이용하세요."
        )

    # douyin/tiktok 외 URL은 yt-dlp 결과만 반환
    return None, err1


# ── YouTube 추천 영상 시스템 (7차) ──
def generate_youtube_keywords(product_name, category="기타"):
    """제품명 → YouTube 검색용 영어 키워드 5개 생성."""
    if has_key("ANTHROPIC_API_KEY") and product_name:
        result = call_claude(
            "YouTube search keyword expert. Output English keywords only, one per line, no numbering.",
            f"Product: {product_name}\nCategory: {category}\n\n"
            "Generate 5 YouTube search keywords in English for finding short review/demo videos.\n"
            "Each keyword 2-4 words, one per line.\nFocus: product review, comparison, how-to, demo, shorts.",
            max_tokens=200
        )
        if result:
            keywords = [line.strip() for line in result.strip().split("\n") if line.strip() and not line.strip().startswith("#")]
            return keywords[:5]
    # Fallback
    base = _translate_keyword_to_english(product_name) if product_name else "product"
    return [f"{base} review", f"{base} unboxing", f"best {base}", f"{base} shorts", f"{base} demo"]


def search_youtube_recommendations(keywords, max_results=5):
    """yt-dlp ytsearch로 추천 영상 검색. 키워드별 3개 → 중복제거 → ≤90초 → top N."""
    all_results = []
    seen_ids = set()
    for kw in keywords:
        try:
            cmd = [
                "yt-dlp", f"ytsearch3:{kw}",
                "--flat-playlist",
                "--print", "%(id)s|||%(title)s|||%(duration)s|||%(channel)s|||%(view_count)s|||%(url)s",
                "--no-check-certificates",
                "--socket-timeout", "15",
            ]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                continue
            for line in r.stdout.strip().split("\n"):
                if not line.strip() or "|||" not in line:
                    continue
                parts = line.strip().split("|||")
                if len(parts) < 6:
                    continue
                vid_id, title, dur_raw, channel, views_raw, url = parts[0], parts[1], parts[2], parts[3], parts[4], parts[5]
                if vid_id in seen_ids:
                    continue
                seen_ids.add(vid_id)
                try:
                    dur_sec = int(float(dur_raw)) if dur_raw and dur_raw != "NA" else 0
                except (ValueError, TypeError):
                    dur_sec = 0
                if dur_sec > 90:
                    continue
                # 조회수 포맷
                try:
                    vc = int(views_raw) if views_raw and views_raw != "NA" else 0
                    if vc >= 1_000_000:
                        views_text = f"{vc/1_000_000:.1f}M"
                    elif vc >= 1_000:
                        views_text = f"{vc/1_000:.1f}K"
                    else:
                        views_text = str(vc) if vc else ""
                except (ValueError, TypeError):
                    views_text = ""
                dur_min = dur_sec // 60
                dur_s = dur_sec % 60
                dur_str = f"{dur_min}:{dur_s:02d}" if dur_sec > 0 else "0:00"
                is_short = "/shorts/" in url or dur_sec <= 60
                thumb_url = f"https://img.youtube.com/vi/{vid_id}/hqdefault.jpg"
                all_results.append({
                    "id": vid_id, "title": title, "url": url,
                    "thumbnail": thumb_url, "channel": channel, "duration": dur_str,
                    "dur_sec": dur_sec, "views": views_text, "is_short": is_short, "keyword": kw,
                })
        except Exception:
            continue
    all_results.sort(key=lambda x: (not x["is_short"], x["dur_sec"]))
    return all_results[:max_results]


def extract_product_videos(url):
    """쿠팡/아마존 URL에서 제품 동영상 URL 추출"""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    videos = []
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")

        # video/source 태그 직접 검색
        for tag in soup.find_all(["video", "source"]):
            src = tag.get("src") or tag.get("data-src") or ""
            if src and (".mp4" in src or ".webm" in src):
                if src.startswith("//"):
                    src = "https:" + src
                if src not in [v["url"] for v in videos]:
                    videos.append({"url": src, "alt": "제품 영상"})

        # script 태그 내 mp4 URL 추출
        for script in soup.find_all("script"):
            text = script.string or ""
            mp4s = re.findall(r'https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*', text)
            for vu in mp4s:
                clean = vu.split('"')[0].split("'")[0]
                if clean not in [v["url"] for v in videos]:
                    videos.append({"url": clean, "alt": "제품 영상"})

        # data 속성에서 영상 URL
        for el in soup.find_all(attrs={"data-video-url": True}):
            vu = el["data-video-url"]
            if vu.startswith("//"):
                vu = "https:" + vu
            if vu not in [v["url"] for v in videos]:
                videos.append({"url": vu, "alt": "제품 영상"})

    except:
        pass
    return videos[:5]

def auto_order_clips(clips):
    """클립 usage_tag/소스/이름 기반 최적 순서 추천: 인트로 → 제품소개 → 사용장면 → 아웃트로"""
    intro, product, usage, background, outro, other = [], [], [], [], [], []
    for i, c in enumerate(clips):
        tag = c.get("usage_tag", "")
        name = c.get("name", "").lower()
        source = c.get("source", "")
        # usage_tag 우선
        if tag == "인트로":
            intro.append(i)
        elif tag == "아웃트로":
            outro.append(i)
        elif tag == "제품소개":
            product.append(i)
        elif tag == "사용장면":
            usage.append(i)
        # usage_tag 없으면 name/source fallback
        elif "[인트로]" in name or "intro" in name:
            intro.append(i)
        elif "[아웃트로]" in name or "outro" in name:
            outro.append(i)
        elif source == "kenburns" or "제품" in name or "product" in name:
            product.append(i)
        elif "[배경]" in name or "background" in name or source == "pexels":
            background.append(i)
        else:
            other.append(i)
    order = intro + product + usage + other + background + outro
    return [clips[i] for i in order]

def get_video_duration(path):
    try:
        res = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=10
        )
        return float(json.loads(res.stdout)["format"]["duration"])
    except:
        return 0

# ═══════════════════════════════════════════════════════════════
# 조회수 최적화 헬퍼 함수
# ═══════════════════════════════════════════════════════════════

def generate_hooks(product_name, category="기타", content_mode="클릭유도형", count=3):
    """AI로 Hook 텍스트(A/B/C) 생성. API 없으면 템플릿 fallback."""
    hook_types = [
        ("A", "문제 제시형", f"{product_name} 때문에 고민이셨죠? 이거 하나면 해결됩니다"),
        ("B", "놀람형", f"이거 하나로 끝났습니다, 왜 이제 알았지… {product_name}"),
        ("C", "손해 회피형", f"이거 모르면 계속 손해봅니다, {product_name} 지금 바로 확인하세요"),
    ]
    if has_key("ANTHROPIC_API_KEY"):
        try:
            result = call_claude(
                "숏폼 Hook 전문가. 각 유형별 1문장만 출력. 번호 붙여서.",
                f"제품: {product_name}\n카테고리: {category}\n콘텐츠 목적: {content_mode}\n\n"
                "아래 3가지 유형으로 숏폼 첫 3초 Hook 문장을 1개씩 만들어줘.\n"
                "A) 문제 제시형: 시청자 문제 공감 → 해결 암시\n"
                "B) 놀람형: 결과 먼저 보여주고 궁금증 유발\n"
                "C) 손해 회피형: 안 쓰면 손해라는 긴박감\n\n"
                "조건: 각 20자 이내, 이모지 금지, 말투는 구어체\n"
                "형식: A) 문장\\nB) 문장\\nC) 문장"
            )
            if result:
                lines = [l.strip() for l in result.strip().split("\n") if l.strip()]
                parsed = []
                for l in lines:
                    clean = l.lstrip("ABC)）: ·•-").strip()
                    if clean:
                        parsed.append(clean)
                if len(parsed) >= 3:
                    return [
                        {"name": "A", "type": "문제 제시형", "hook_text": parsed[0]},
                        {"name": "B", "type": "놀람형", "hook_text": parsed[1]},
                        {"name": "C", "type": "손해 회피형", "hook_text": parsed[2]},
                    ][:count]
        except:
            pass
    # fallback: 템플릿 기반
    return [{"name": h[0], "type": h[1], "hook_text": h[2]} for h in hook_types[:count]]


def ensure_hook_clip_duration(clip_path, min_dur=3.0):
    """Hook 클립이 min_dur보다 짧으면 loop/freeze로 보장. 원본 이상이면 trim."""
    dur = get_video_duration(clip_path)
    if dur <= 0:
        return clip_path, min_dur
    if dur >= min_dur:
        # trim to min_dur
        tmp = _ensure_dir("shortform_hooks")
        out = tmp / f"hook_trim_{int(min_dur)}s.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-i", clip_path,
            "-t", str(min_dur),
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            str(out)
        ], capture_output=True, text=True, timeout=30)
        return str(out) if out.exists() else clip_path, min_dur
    # dur < min_dur → loop
    loops_needed = int(min_dur / dur) + 1
    tmp = _ensure_dir("shortform_hooks")
    concat_file = tmp / "hook_loop.txt"
    with open(concat_file, "w") as f:
        for _ in range(loops_needed):
            f.write(f"file '{clip_path}'\n")
    out = tmp / f"hook_loop_{int(min_dur)}s.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-t", str(min_dur),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        str(out)
    ], capture_output=True, text=True, timeout=30)
    return str(out) if out.exists() else clip_path, min_dur


def build_pattern_interrupt_filters(total_dur, hook_dur=3.0):
    """Pattern Interrupt FFmpeg 필터 리스트 생성. Hook 구간(0~hook_dur) 제외."""
    filters = []
    if total_dur <= hook_dur + 1:
        return filters
    body_dur = total_dur - hook_dur
    # 10% 지점: zoom in (1.15x, 0.5초간) — scale+crop 기반 (동영상 스트림 호환)
    t_zoom = hook_dur + body_dur * 0.10
    z = 1.15
    filters.append(
        f"scale=iw*{z}:-1:enable='between(t,{t_zoom:.1f},{t_zoom+0.5:.1f})',"
        f"crop=iw/{z}:ih/{z}:enable='between(t,{t_zoom:.1f},{t_zoom+0.5:.1f})'"
    )
    # 25% 지점: 0.15초 jump cut (밝기 깜빡임으로 시뮬레이션)
    t_cut = hook_dur + body_dur * 0.25
    filters.append(
        f"eq=brightness=0.08:enable='between(t,{t_cut:.2f},{t_cut+0.15:.2f})'"
    )
    # 60% 지점: flash (시각적 whoosh 대체)
    t_whoosh = hook_dur + body_dur * 0.60
    filters.append(
        f"eq=brightness=0.12:enable='between(t,{t_whoosh:.2f},{t_whoosh+0.10:.2f})'"
    )
    return filters


def build_pi_subtitle_emphasis(subs, total_dur, hook_dur=3.0):
    """40% 지점 자막 키워드 강조 — ASS 자막 수정용 정보 반환."""
    if not subs or total_dur <= hook_dur + 1:
        return None
    body_dur = total_dur - hook_dur
    t_emphasis = hook_dur + body_dur * 0.40
    # 해당 시점의 자막 찾기
    for s in subs:
        if s["start"] <= t_emphasis <= s["end"]:
            return {"time": t_emphasis, "text": s["text"], "start": s["start"], "end": s["end"]}
    return None


def build_retention_booster_filters(total_dur, subs=None, hook_dur=3.0):
    """Retention Booster FFmpeg 필터 리스트 생성."""
    filters = []
    if total_dur <= 5:
        return filters
    # 규칙 2: 2초마다 미세 zoom 변화 (hook 이후)
    t = hook_dur + 2.0
    zoom_toggle = True
    while t < total_dur - 2:
        z = 1.03 if zoom_toggle else 1.0
        filters.append(
            f"eq=brightness={'0.03' if not zoom_toggle else '-0.02'}:"
            f"enable='between(t,{t:.1f},{t+0.3:.1f})'"
        )
        zoom_toggle = not zoom_toggle
        t += 2.0
    return filters


def build_retention_subtitle_mods(subs, total_dur, hook_dur=3.0):
    """Retention Booster 자막 수정 정보 반환: 첫 5초 밀도 증가 + Benefit 강조."""
    mods = {"dense_first_5s": False, "benefit_emphasis": None}
    if not subs:
        return mods
    # 규칙 1: 첫 5초 자막 밀도 — 첫 5초 내 자막이 2개 미만이면 분할 필요 표시
    early_subs = [s for s in subs if s["start"] < hook_dur + 5.0 and s["start"] >= hook_dur]
    if len(early_subs) < 2 and early_subs:
        mods["dense_first_5s"] = True
    # 규칙 3: 중간 구간 Benefit 강조 (40~70% 지점)
    mid_start = total_dur * 0.4
    mid_end = total_dur * 0.7
    for s in subs:
        if mid_start <= s["start"] <= mid_end:
            mods["benefit_emphasis"] = {"text": s["text"], "start": s["start"], "end": s["end"]}
            break
    return mods


def merge_tts_audio(hook_tts_path, body_tts_path, output_path, hook_dur=3.0):
    """Hook TTS + Body TTS를 이어붙임. Hook TTS는 hook_dur에 맞게 padding/trim."""
    tmp = _ensure_dir("shortform_hooks")
    # Hook TTS를 정확히 hook_dur로 맞추기
    hook_adjusted = tmp / "hook_tts_adjusted.mp3"
    hook_audio_dur = get_audio_duration(hook_tts_path) if os.path.exists(hook_tts_path) else 0
    if hook_audio_dur > 0:
        if hook_audio_dur > hook_dur:
            # trim
            subprocess.run([
                "ffmpeg", "-y", "-i", hook_tts_path, "-t", str(hook_dur),
                "-c:a", "aac", "-b:a", "128k", str(hook_adjusted)
            ], capture_output=True, text=True, timeout=15)
        elif hook_audio_dur < hook_dur:
            # pad with silence
            pad = hook_dur - hook_audio_dur
            subprocess.run([
                "ffmpeg", "-y", "-i", hook_tts_path,
                "-af", f"apad=pad_dur={pad:.2f}",
                "-c:a", "aac", "-b:a", "128k", str(hook_adjusted)
            ], capture_output=True, text=True, timeout=15)
        else:
            import shutil
            shutil.copy2(hook_tts_path, str(hook_adjusted))
    else:
        # Hook TTS 없으면 무음 생성
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=mono",
            "-t", str(hook_dur), "-c:a", "aac", "-b:a", "128k", str(hook_adjusted)
        ], capture_output=True, text=True, timeout=15)

    if not hook_adjusted.exists():
        return body_tts_path  # fallback

    # body_tts도 동일 코덱(aac, 44100Hz)으로 재인코딩하여 concat 안정성 확보
    body_adjusted = tmp / "body_tts_adjusted.m4a"
    if body_tts_path and os.path.exists(body_tts_path):
        try:
            subprocess.run([
                "ffmpeg", "-y", "-i", body_tts_path,
                "-ar", "44100", "-ac", "1", "-c:a", "aac", "-b:a", "128k",
                str(body_adjusted)
            ], capture_output=True, text=True, timeout=30)
        except:
            body_adjusted = Path(body_tts_path)  # fallback: 원본 사용
        if not body_adjusted.exists():
            body_adjusted = Path(body_tts_path)
    else:
        body_adjusted = None

    # concat hook + body
    concat_file = tmp / "tts_concat.txt"
    with open(concat_file, "w") as f:
        f.write(f"file '{hook_adjusted}'\n")
        if body_adjusted and body_adjusted.exists():
            f.write(f"file '{body_adjusted}'\n")
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-ar", "44100", "-ac", "1", "-c:a", "aac", "-b:a", "128k", str(output_path)
    ], capture_output=True, text=True, timeout=30)
    return str(output_path) if os.path.exists(output_path) else body_tts_path


def generate_hook_subtitles(hook_text, hook_dur=3.0, body_subs=None):
    """Hook 자막 + Body 자막(offset 적용) 결합."""
    # Hook 자막: 0초부터 hook_dur까지
    hook_sub = [{"start": 0.0, "end": min(hook_dur, max(1.5, len(hook_text) * 0.15)), "text": hook_text}]
    if not body_subs:
        return hook_sub
    # Body 자막: hook_dur 이후로 offset
    merged = list(hook_sub)
    for s in body_subs:
        merged.append({
            "start": round(s["start"] + hook_dur, 1),
            "end": round(s["end"] + hook_dur, 1),
            "text": s["text"]
        })
    return merged


def assemble_hook_versions(clips, body_subs, body_tts_path, target_dur, crop_ratio="9:16",
                           ass_path=None, bgm_path=None, bgm_volume=0.2,
                           cta_text=None, cta_position="하단", cta_duration=3, cta_color="#FFFFFF",
                           hook_clip_path=None, hooks=None, hook_dur=3.0,
                           pattern_interrupt=False, retention_booster=False, anti_shadowban=False):
    """Hook A/B/C 버전별 영상 생성. assemble_video()를 재사용."""
    if not hooks or not clips:
        return []
    results = []
    tmp = _ensure_dir("shortform_hooks")
    # Hook 클립 준비 (3초 보장)
    base_hook_path = hook_clip_path or clips[0]["path"]
    hook_clip_ready, actual_hook_dur = ensure_hook_clip_duration(base_hook_path, hook_dur)

    for hook_info in hooks:
        ver_name = hook_info["name"]
        hook_text = hook_info["hook_text"]
        # 1. Hook TTS 생성 (generate_tts_auto 사용)
        hook_tts_out = tmp / f"hook_tts_{ver_name}.mp3"
        hook_tts_generated = False
        try:
            hook_tts_generated = generate_tts_auto(hook_text, str(hook_tts_out))
        except:
                pass

        # 2. TTS 병합 (hook_tts + body_tts)
        merged_tts = tmp / f"merged_tts_{ver_name}.mp3"
        if hook_tts_generated and body_tts_path and os.path.exists(body_tts_path):
            merge_tts_audio(str(hook_tts_out), body_tts_path, str(merged_tts), hook_dur)
            final_tts = str(merged_tts) if merged_tts.exists() else body_tts_path
        elif body_tts_path and os.path.exists(body_tts_path):
            final_tts = body_tts_path
        else:
            final_tts = None

        # 3. 자막 결합 (hook 자막 + body 자막 offset)
        merged_subs = generate_hook_subtitles(hook_text, hook_dur, body_subs)

        # 4. 클립 리스트: hook_clip + body_clips
        hook_clip_dict = {
            "name": f"hook_{ver_name}.mp4",
            "path": hook_clip_ready,
            "duration": f"0:{int(hook_dur):02d}",
            "dur_sec": hook_dur,
            "source": "hook",
        }
        version_clips = [hook_clip_dict] + list(clips)

        # 5. ASS 자막 재생성 (offset 적용된 merged_subs로)
        ver_ass_path = None
        try:
            fontpath = find_korean_font()
            pn = st.session_state.get("_w_pname", "") or st.session_state.get("_saved_pname", "") or st.session_state.get("coupang_product", "")
            ver_ass_path = generate_ass_subtitle(
                merged_subs, fontpath, product_name=pn,
                sub_size=60, sub_pos=2, sub_col="&H00FFFFFF",
                sub_bold=True, sub_anim="없음", sub_margin=50
            )
        except:
            ver_ass_path = None

        # 6. assemble_video 호출
        output, err = assemble_video(
            version_clips, merged_subs, final_tts, target_dur,
            crop_ratio=crop_ratio, ass_path=ver_ass_path,
            bgm_path=bgm_path, bgm_volume=bgm_volume,
            cta_text=cta_text, cta_position=cta_position,
            cta_duration=cta_duration, cta_color=cta_color,
            pattern_interrupt=pattern_interrupt,
            retention_booster=retention_booster,
            anti_shadowban=anti_shadowban
        )

        # 7. 결과 이름 변경
        if output and os.path.exists(output):
            final_out = tmp / f"hook_version_{ver_name}.mp4"
            import shutil
            shutil.copy2(output, str(final_out))
            results.append({
                "name": ver_name,
                "type": hook_info["type"],
                "hook_text": hook_text,
                "video_path": str(final_out),
                "subtitle_path": ver_ass_path or "",
                "audio_path": final_tts or "",
            })
        else:
            results.append({
                "name": ver_name,
                "type": hook_info["type"],
                "hook_text": hook_text,
                "video_path": "",
                "subtitle_path": "",
                "audio_path": "",
                "error": err or "조립 실패",
            })
    return results


# ── Anti-Shadowban 경량 딥에디팅 필터 ──
def _build_anti_shadowban_vfilters():
    """Anti-Shadowban 비디오 필터 생성: 속도/밝기/대비/좌우반전."""
    import random
    filters = []
    speed = 1.0 + random.uniform(0.02, 0.05)
    filters.append(f"setpts=PTS/{speed:.4f}")
    brightness = random.uniform(-0.02, 0.02)
    contrast = 1.0 + random.uniform(-0.02, 0.02)
    filters.append(f"eq=brightness={brightness:.4f}:contrast={contrast:.4f}")
    if random.random() < 0.5:
        filters.append("hflip")
    return filters, speed

def _get_anti_shadowban_sub_offset():
    """Anti-Shadowban 자막 위치 오프셋 (±10px)."""
    import random
    return random.randint(-10, 10)

def _get_anti_shadowban_bgm_filter():
    """Anti-Shadowban BGM 피치 변조."""
    import random
    rate = random.uniform(0.99, 1.01)
    return f"asetrate=44100*{rate:.4f},aresample=44100"


def assemble_video(clips, subs, tts_path, target_dur, crop_ratio="9:16", ass_path=None, bgm_path=None, bgm_volume=0.2, cta_text=None, cta_position="하단", cta_duration=3, cta_color="#FFFFFF", pattern_interrupt=False, retention_booster=False, anti_shadowban=False):
    """FFmpeg로 실제 영상 조립 (에러 체크 포함, ASS 자막 + BGM 믹싱 지원)"""
    tmp = _ensure_dir("shortform_build")

    # 1. 클립 파일 확인
    valid_clips = [c for c in clips if os.path.exists(c["path"])]
    if not valid_clips:
        return None, "클립 파일이 없습니다."

    # 2. concat 파일 생성 (특수문자 파일명 → 안전한 임시 복사본)
    import re as _re
    import shutil as _shutil
    _safe_dir = _ensure_dir("shortform_build/safe_clips")
    _safe_paths = []
    for _ci, c in enumerate(valid_clips):
        _orig = c["path"]
        _basename = os.path.basename(_orig)
        # ASCII 알파벳/숫자/점/하이픈/밑줄만 허용, 나머지 제거
        _safe_name = _re.sub(r'[^a-zA-Z0-9._-]', '', _basename)
        if not _safe_name or _safe_name.startswith('.'):
            _safe_name = f"clip_{_ci}.mp4"
        _safe_path = str(_safe_dir / f"c{_ci}_{_safe_name}")
        try:
            _shutil.copy2(_orig, _safe_path)
            _safe_paths.append(_safe_path)
        except Exception:
            _safe_paths.append(_orig)  # 복사 실패 시 원본 사용

    concat_file = tmp / "filelist.txt"
    with open(concat_file, "w", encoding="utf-8") as f:
        for _sp in _safe_paths:
            # FFmpeg concat 형식: 경로를 '로 감싸고, 내부 ' → '\'' 이스케이프
            _escaped = _sp.replace("'", "'\\''")
            f.write(f"file '{_escaped}'\n")

    concat_out = tmp / "concat.mp4"

    # 3. 클립 연결 (re-encode for compatibility)
    r1 = subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-t", str(target_dur),
        str(concat_out)
    ], capture_output=True, text=True, timeout=120)

    if r1.returncode != 0 or not concat_out.exists():
        return None, f"영상 클립 연결에 실패했습니다. 클립 파일이 손상되었거나 형식이 다를 수 있어요."

    # 4. 9:16 크롭 + 자막 오버레이
    vf_filters = []

    # 크롭
    if crop_ratio == "9:16":
        vf_filters.append("scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920")
    else:
        vf_filters.append("scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080")

    # Anti-Shadowban 비디오 필터
    _as_speed = 1.0
    _as_bgm_filter = None
    if anti_shadowban:
        _as_vfilters, _as_speed = _build_anti_shadowban_vfilters()
        vf_filters.extend(_as_vfilters)
        _as_bgm_filter = _get_anti_shadowban_bgm_filter()

    # 자막: ASS 파일 우선 → drawtext fallback
    if ass_path and os.path.exists(ass_path):
        # ASS 자막 필터 (키워드 하이라이트, 외곽선, 그림자 포함)
        ass_escaped = str(ass_path).replace("\\", "/").replace(":", "\\:")
        vf_filters.append(f"ass='{ass_escaped}'")
    elif subs:
        fontpath = find_korean_font()
        if fontpath:
            fontpath_escaped = fontpath.replace("\\", "/").replace(":", "\\:")
            for s in subs:
                text = s["text"].replace("'", "\u2019").replace(":", "\\:").replace(",", "\\,")
                vf_filters.append(
                    f"drawtext=fontfile='{fontpath_escaped}':text='{text}':"
                    f"fontcolor=white:fontsize=48:borderw=3:"
                    f"x=(w-text_w)/2:y=h-200:shadowcolor=black:shadowx=3:shadowy=3:"
                    f"enable='between(t,{s['start']},{s['end']})'"
                )
        else:
            st.warning("한글 폰트를 찾을 수 없어 자막 없이 조립합니다.")

    # CTA 오버레이 (마지막 N초에만 표시)
    if cta_text and cta_text.strip():
        cta_fontpath = find_korean_font()
        if cta_fontpath:
            cta_fp_esc = cta_fontpath.replace("\\", "/").replace(":", "\\:")
            cta_t = cta_text.strip().replace("'", "\u2019").replace(":", "\\:").replace(",", "\\,")
            cta_start = max(0, target_dur - cta_duration)
            # Retention Booster ON 시 CTA 타이밍 최적화: 마지막 2초 전 노출
            if retention_booster and target_dur > 5:
                cta_start = max(0, target_dur - 2 - cta_duration)
            # 위치: 상단/하단/중앙하단 (자막과 충돌 방지)
            if cta_position == "상단":
                cta_y = "100"
            elif cta_position == "중앙하단":
                cta_y = "h*0.65"
            else:  # 하단 (기본) — 자막보다 위
                cta_y = "h-350"
            vf_filters.append(
                f"drawtext=fontfile='{cta_fp_esc}':text='{cta_t}':"
                f"fontcolor={cta_color}:fontsize=42:borderw=2:"
                f"x=(w-text_w)/2:y={cta_y}:"
                f"box=1:boxcolor=black@0.5:boxborderw=12:"
                f"enable='gte(t,{cta_start})'"
            )

    # ── Pattern Interrupt 필터 ──
    if pattern_interrupt:
        pi_filters = build_pattern_interrupt_filters(target_dur, hook_dur=3.0)
        vf_filters.extend(pi_filters)
        # 40% 지점 자막 키워드 강조 (drawtext 추가)
        pi_emphasis = build_pi_subtitle_emphasis(subs, target_dur, hook_dur=3.0)
        if pi_emphasis:
            emp_fontpath = find_korean_font()
            if emp_fontpath:
                emp_fp = emp_fontpath.replace("\\", "/").replace(":", "\\:")
                emp_txt = pi_emphasis["text"].replace("'", "\u2019").replace(":", "\\:").replace(",", "\\,")
                vf_filters.append(
                    f"drawtext=fontfile='{emp_fp}':text='{emp_txt}':"
                    f"fontcolor=yellow:fontsize=64:borderw=4:"
                    f"x=(w-text_w)/2:y=h*0.35:"
                    f"shadowcolor=black:shadowx=3:shadowy=3:"
                    f"enable='between(t,{pi_emphasis['start']:.1f},{pi_emphasis['end']:.1f})'"
                )

    # ── Retention Booster 필터 ──
    if retention_booster:
        rb_filters = build_retention_booster_filters(target_dur, hook_dur=3.0)
        vf_filters.extend(rb_filters)
        # Benefit 강조 (drawtext)
        rb_mods = build_retention_subtitle_mods(subs, target_dur, hook_dur=3.0)
        if rb_mods.get("benefit_emphasis"):
            be = rb_mods["benefit_emphasis"]
            be_fontpath = find_korean_font()
            if be_fontpath:
                be_fp = be_fontpath.replace("\\", "/").replace(":", "\\:")
                be_txt = be["text"].replace("'", "\u2019").replace(":", "\\:").replace(",", "\\,")
                vf_filters.append(
                    f"drawtext=fontfile='{be_fp}':text='{be_txt}':"
                    f"fontcolor=#FFD700:fontsize=72:borderw=5:"
                    f"x=(w-text_w)/2:y=h*0.30:"
                    f"shadowcolor=black:shadowx=4:shadowy=4:"
                    f"enable='between(t,{be['start']:.1f},{be['end']:.1f})'"
                )
        # CTA 타이밍 최적화: 마지막 2초 전으로 조정
        # (이미 cta_start가 위에서 계산되었으므로 여기서는 별도 처리 불필요)

    final_out = tmp / "final.mp4"
    vf_str = ",".join(vf_filters) if vf_filters else "null"

    cmd = ["ffmpeg", "-y", "-i", str(concat_out)]

    # TTS + BGM 오디오 합성
    has_tts = tts_path and os.path.exists(tts_path)
    has_bgm = bgm_path and os.path.exists(bgm_path)

    if has_tts:
        cmd += ["-i", tts_path]
    if has_bgm:
        cmd += ["-stream_loop", "-1", "-i", bgm_path]

    # Anti-Shadowban BGM 피치 시프트
    _bgm_pre = f",{_as_bgm_filter}" if (anti_shadowban and _as_bgm_filter) else ""

    if has_tts and has_bgm:
        tts_idx, bgm_idx = 1, 2
        cmd += ["-filter_complex",
                f"[{bgm_idx}:a]volume={bgm_volume}{_bgm_pre}[bgml];[{tts_idx}:a][bgml]amix=inputs=2:duration=first:dropout_transition=2[aout]",
                "-vf", vf_str, "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-map", "0:v", "-map", "[aout]", "-c:a", "aac", "-shortest",
                str(final_out)]
    elif has_tts:
        cmd += ["-vf", vf_str, "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-shortest",
                str(final_out)]
    elif has_bgm:
        bgm_idx = 1
        cmd += ["-filter_complex",
                f"[{bgm_idx}:a]volume={bgm_volume}{_bgm_pre}[bgm]",
                "-vf", vf_str, "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-map", "0:v", "-map", "[bgm]", "-c:a", "aac", "-shortest",
                str(final_out)]
    else:
        cmd += ["-vf", vf_str, "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac", str(final_out)]

    r2 = subprocess.run(cmd, capture_output=True, text=True, timeout=180)

    if r2.returncode != 0 or not final_out.exists():
        return None, f"영상 합성 실패: {r2.stderr[-300:] if r2.stderr else 'unknown error'}"

    return str(final_out), None

def scrape_og_tags(url):
    """URL에서 OG 태그(og:title, og:image, og:description) 추출.
    Selenium 없이 requests + BeautifulSoup만 사용."""
    result = {"og_title": "", "og_image": "", "og_description": "", "success": False}
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        resp = requests.get(url, headers=headers, timeout=8)
        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        og_title = soup.find("meta", property="og:title")
        og_image = soup.find("meta", property="og:image")
        og_desc = soup.find("meta", property="og:description")
        if og_title and og_title.get("content"):
            result["og_title"] = og_title["content"].strip()
        if og_image and og_image.get("content"):
            img_url = og_image["content"].strip()
            if img_url.startswith("//"):
                img_url = "https:" + img_url
            result["og_image"] = img_url
        if og_desc and og_desc.get("content"):
            result["og_description"] = og_desc["content"].strip()
        if result["og_title"] or result["og_image"]:
            result["success"] = True
    except Exception:
        pass
    return result

def parse_coupang_share_text(text: str) -> dict:
    """쿠팡 앱 '공유' 텍스트에서 상품명 + URL 자동 분리.

    예상 입력 (쿠팡 앱 공유):
        "[쿠팡] 닥터자르트 시카페어 토너 200ml\nhttps://link.coupang.com/a/exnTX4"
        또는
        "닥터자르트 시카페어 토너 200ml https://link.coupang.com/a/abc"
        또는 단순 URL만

    Returns:
        {"name": str, "url": str, "success": bool}
    """
    if not text:
        return {"name": "", "url": "", "success": False}

    text = text.strip()

    # URL 추출 (link.coupang.com 또는 coupang.com)
    url_match = re.search(
        r'https?://(?:link\.coupang\.com/a/[A-Za-z0-9]+'
        r'|(?:www|m)\.coupang\.com/[^\s]+)',
        text,
    )
    extracted_url = url_match.group(0) if url_match else ""

    # 상품명 = URL을 제외한 나머지 (특수 문자/접두사 제거)
    name_part = text
    if extracted_url:
        name_part = name_part.replace(extracted_url, "").strip()

    # 흔한 접두사 제거
    for prefix in ("[쿠팡]", "쿠팡:", "Coupang:", "쿠팡-"):
        if name_part.startswith(prefix):
            name_part = name_part[len(prefix):].strip()

    # 줄바꿈/탭 정리
    name_part = re.sub(r'\s+', ' ', name_part).strip()

    # 너무 짧거나 길면 무효
    valid_name = len(name_part) >= 3 and len(name_part) <= 200

    return {
        "name": name_part if valid_name else "",
        "url": extracted_url,
        "success": bool(extracted_url or valid_name),
    }


def extract_coupang_info(url):
    """쿠팡 URL에서 제품명 추출 시도.

    지원:
    - link.coupang.com/a/XXX (단축 URL) → 302 Location에서 productId 추출
    - www.coupang.com/vp/products/XXX (긴 URL) → 일반 추출 시도

    중요: 쿠팡은 상품 상세 페이지를 HTTP 403으로 차단함.
    단축 URL은 redirect까지는 OK이므로 productId만 확실히 추출됨.

    Returns: {"name": str, "success": bool, "error": str, "product_id": str}
    """
    product_id = ""

    # ── 단축 URL (link.coupang.com) 처리 ──
    if "link.coupang.com" in url:
        try:
            short_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Accept-Language": "ko-KR,ko;q=0.9",
            }
            r = requests.get(url, headers=short_headers, timeout=10, allow_redirects=False)
            if r.status_code in (301, 302, 303, 307, 308):
                location = r.headers.get("Location", "")
                # Location URL에서 productId 추출
                pid_m = re.search(r'products/(\d+)', location)
                if pid_m:
                    product_id = pid_m.group(1)
                    return {
                        "name": f"쿠팡 상품 #{product_id}",
                        "success": False,  # 상품명은 못 가져옴 (수동 입력 필요)
                        "product_id": product_id,
                        "error": ("단축 URL에서 상품 ID는 추출했지만 상품명은 쿠팡이 차단합니다. "
                                  "쿠팡 앱/사이트에서 상품명을 복사해 입력해주세요."),
                    }
        except Exception as e:
            return {
                "name": "", "success": False, "product_id": "",
                "error": f"단축 URL 처리 실패: {type(e).__name__}",
            }

    # ── 일반 긴 URL의 productId 추출 ──
    pid_match = re.search(r'products/(\d+)', url)
    if pid_match:
        product_id = pid_match.group(1)

    base_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Sec-Ch-Ua": '"Chromium";v="131", "Google Chrome";v="131"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "Referer": "https://www.google.com/",
    }

    # 시도 순서: PC 사이트 → 모바일 사이트
    attempts = [
        ("PC", url, base_headers),
        ("Mobile", url.replace("www.coupang.com", "m.coupang.com"),
         {**base_headers, "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                                          "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                                          "Version/17.0 Mobile/15E148 Safari/604.1"}),
    ]

    last_error = "알 수 없는 오류"
    for label, _url, _headers in attempts:
        try:
            resp = requests.get(_url, headers=_headers, timeout=10)
            resp.encoding = resp.apparent_encoding or "utf-8"
            if resp.status_code == 403:
                last_error = f"쿠팡이 자동 추출을 차단했습니다 (HTTP 403). 제품명을 직접 입력해주세요."
                continue
            if resp.status_code != 200:
                last_error = f"HTTP {resp.status_code} ({label})"
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            og_title = soup.find("meta", property="og:title")
            if og_title and og_title.get("content"):
                name = og_title["content"].replace(" - 쿠팡!", "").replace(" | 쿠팡", "").strip()
                if name and len(name) > 2:
                    return {"name": name, "success": True, "product_id": product_id, "error": ""}
            match = re.search(r'<title>(.*?)</title>', resp.text)
            if match:
                title = match.group(1).replace(" - 쿠팡!", "").replace(" | 쿠팡", "").strip()
                if title and len(title) > 2:
                    return {"name": title, "success": True, "product_id": product_id, "error": ""}
            last_error = f"OG 태그 + title 태그 모두 없음 ({label})"
        except Exception as e:
            last_error = f"{type(e).__name__}: {str(e)[:80]}"

    # 모든 시도 실패 — productId placeholder
    return {
        "name": f"쿠팡 상품 #{product_id}" if product_id else "",
        "success": False,
        "product_id": product_id,
        "error": last_error,
    }

def extract_product_images(url):
    """쿠팡/아마존 URL에서 제품 이미지 URL 추출"""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    images = []
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")

        # 1) og:image (메타 태그)
        og = soup.find("meta", property="og:image")
        if og and og.get("content"):
            images.append({"url": og["content"], "alt": "대표 이미지"})

        if "coupang.com" in url:
            # 쿠팡: 상품 상세 이미지
            for img in soup.select("img.prod-image__detail, img[data-img-src], .prod-image img, .subType-IMAGE img"):
                src = img.get("data-img-src") or img.get("src") or ""
                if src and ("thumbnail" in src or "image" in src or "coupangcdn" in src):
                    if src.startswith("//"):
                        src = "https:" + src
                    if src not in [i["url"] for i in images]:
                        images.append({"url": src, "alt": img.get("alt", "")[:40]})
            # 쿠팡: 큰 이미지 패턴
            for img in soup.find_all("img"):
                src = img.get("src") or img.get("data-img-src") or ""
                if "coupangcdn" in src and ("500x500" in src or "1000x1000" in src or "230x230" in src):
                    full = re.sub(r'\d+x\d+', '1000x1000', src)
                    if full.startswith("//"):
                        full = "https:" + full
                    if full not in [i["url"] for i in images]:
                        images.append({"url": full, "alt": img.get("alt", "")[:40]})

        elif "amazon" in url:
            # 아마존: 고해상도 이미지
            for img in soup.find_all("img"):
                hires = img.get("data-old-hires") or ""
                if hires and hires not in [i["url"] for i in images]:
                    images.append({"url": hires, "alt": img.get("alt", "")[:40]})
            landing = soup.find("img", id="landingImage")
            if landing:
                src = landing.get("data-old-hires") or landing.get("src") or ""
                if src and src not in [i["url"] for i in images]:
                    images.append({"url": src, "alt": "메인 이미지"})
    except:
        pass

    # 중복 제거 + 최대 15장
    seen = set()
    unique = []
    for img in images:
        if img["url"] not in seen and img["url"].startswith("http"):
            seen.add(img["url"])
            unique.append(img)
    return unique[:15]

def download_image(url, dest_path):
    """이미지 URL을 파일로 다운로드"""
    try:
        r = requests.get(url, stream=True, timeout=15,
                         headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
            return os.path.getsize(dest_path) > 1000
    except:
        pass
    return False

def images_to_kenburns_video(image_paths, dur_per_img=3, output_path=None, resolution="1080x1920"):
    """이미지 리스트 → Ken Burns 효과 슬라이드쇼 영상 생성"""
    if not image_paths:
        return None, "이미지가 없습니다."

    tmp = _ensure_dir("kenburns_build")
    clip_files = []
    effects = ["zoom_in", "zoom_out", "pan_left", "pan_right"]
    w, h = [int(x) for x in resolution.split("x")]
    fps = 30
    frames = dur_per_img * fps

    for idx, img_path in enumerate(image_paths):
        clip_out = tmp / f"kb_{idx}.mp4"
        effect = effects[idx % len(effects)]

        if effect == "zoom_in":
            vf = f"scale=8000:-1,zoompan=z='min(zoom+0.001,1.5)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={resolution}:fps={fps}"
        elif effect == "zoom_out":
            vf = f"scale=8000:-1,zoompan=z='if(eq(on,1),1.5,max(zoom-0.001,1.0))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={resolution}:fps={fps}"
        elif effect == "pan_left":
            vf = f"scale=8000:-1,zoompan=z='1.3':x='iw/2-(iw/zoom/2)-on*2':y='ih/2-(ih/zoom/2)':d={frames}:s={resolution}:fps={fps}"
        else:
            vf = f"scale=8000:-1,zoompan=z='1.3':x='iw/2-(iw/zoom/2)+on*2':y='ih/2-(ih/zoom/2)':d={frames}:s={resolution}:fps={fps}"

        r = subprocess.run([
            "ffmpeg", "-y", "-loop", "1", "-i", str(img_path),
            "-vf", vf, "-t", str(dur_per_img),
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            str(clip_out)
        ], capture_output=True, text=True, timeout=60)

        if r.returncode == 0 and clip_out.exists():
            clip_files.append(str(clip_out))

    if not clip_files:
        return None, "Ken Burns 클립 생성 실패 (FFmpeg 오류)"

    # concat
    concat_file = tmp / "kb_filelist.txt"
    with open(concat_file, "w") as f:
        for cf in clip_files:
            f.write(f"file '{cf}'\n")

    if not output_path:
        output_path = str(tmp / "kenburns_final.mp4")

    r = subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-pix_fmt", "yuv420p",
        str(output_path)
    ], capture_output=True, text=True, timeout=120)

    if r.returncode == 0 and os.path.exists(output_path):
        return str(output_path), None
    return None, f"Ken Burns 합성 실패: {r.stderr[-200:] if r.stderr else 'unknown'}"

def _hex_to_ass_color(hex_color):
    """#RRGGBB → &H00BBGGRR (ASS BGR 포맷)"""
    h = hex_color.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H00{b}{g}{r}"

def _highlight_keywords(text, product_name=""):
    """자막 텍스트에서 키워드를 노란색 ASS 태그로 감싸기"""
    highlight_color = "&H0033E0FF&"  # #FFE033 in ASS BGR
    keywords = ["무료", "할인", "추천", "최저가", "세일", "특가", "무배", "가성비", "쿠팡", "링크"]
    if product_name:
        keywords.append(product_name)
    # 숫자+단위 패턴 (가격, 퍼센트)
    import re as _re
    result = _re.sub(r'(\d[\d,]*\s*(?:원|%|퍼센트|만원|천원|개|배))', rf'{{\\c{highlight_color}}}\1{{\\r}}', text)
    for kw in keywords:
        if kw and kw in result:
            result = result.replace(kw, f'{{\\c{highlight_color}}}{kw}{{\\r}}')
    return result

def generate_ass_subtitle(subs, fontpath, product_name="", sub_size=48, sub_pos="하단 중앙",
                          sub_col="#FFFFFF", sub_bold=True, sub_anim="없음", sub_margin=50):
    """자막 리스트 → ASS 자막 파일 생성, 키워드 하이라이트 포함"""
    tmp = _ensure_dir("shortform_build")
    ass_path = tmp / "subtitle.ass"

    # 폰트명 추출
    fontname = "NanumGothic"
    if fontpath:
        fn = os.path.basename(fontpath).replace(".ttf", "").replace(".ttc", "")
        fontname = fn

    # 색상 변환
    primary_color = _hex_to_ass_color(sub_col)
    outline_color = "&H00000000"  # 검정 외곽선
    shadow_color = "&H80000000"   # 반투명 검정 그림자

    # 위치 → Alignment (numpad 스타일)
    alignment_map = {"하단 중앙": 2, "상단 중앙": 8, "중앙": 5}
    alignment = alignment_map.get(sub_pos, 2)

    bold_val = -1 if sub_bold else 0
    outline = 3
    shadow = 2

    # ASS 헤더
    ass_content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{fontname},{sub_size},{primary_color},&H000000FF,{outline_color},{shadow_color},{bold_val},0,0,0,100,100,0,0,1,{outline},{shadow},{alignment},20,20,{sub_margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    # 이벤트 라인
    for s in subs:
        start_h = int(s["start"] // 3600)
        start_m = int((s["start"] % 3600) // 60)
        start_s = s["start"] % 60
        end_h = int(s["end"] // 3600)
        end_m = int((s["end"] % 3600) // 60)
        end_s = s["end"] % 60

        start_ts = f"{start_h}:{start_m:02d}:{start_s:05.2f}"
        end_ts = f"{end_h}:{end_m:02d}:{end_s:05.2f}"

        # 키워드 하이라이트 적용
        highlighted = _highlight_keywords(s["text"], product_name)

        # 애니메이션 태그
        anim_tag = ""
        if sub_anim == "페이드인/아웃":
            anim_tag = "{\\fad(200,200)}"

        ass_content += f"Dialogue: 0,{start_ts},{end_ts},Default,,0,0,0,,{anim_tag}{highlighted}\n"

    with open(ass_path, "w", encoding="utf-8-sig") as f:
        f.write(ass_content)

    return str(ass_path) if ass_path.exists() else None

def search_pixabay_music(keyword, n=3):
    """Pixabay Music API로 BGM 검색 (실패 시 빈 리스트 반환)"""
    key = get_api_key("PIXABAY_API_KEY")
    if not key:
        return []
    try:
        r = requests.get("https://pixabay.com/api/",
                         params={"key": key, "q": keyword, "per_page": n,
                                 "order": "popular", "safesearch": "true"},
                         timeout=10)
        if r.status_code != 200:
            return []
        data = r.json()
        results = []
        for hit in data.get("hits", []):
            # Pixabay 응답에서 오디오 URL 탐색 (여러 필드 후보)
            audio_url = (hit.get("audio", "") or hit.get("previewURL", "") or
                         hit.get("musicURL", "") or hit.get("webformatURL", ""))
            if audio_url:
                results.append({
                    "id": hit.get("id", 0),
                    "title": (hit.get("title", "") or hit.get("tags", "BGM"))[:40],
                    "url": audio_url,
                    "duration": hit.get("duration", 0),
                    "tags": hit.get("tags", ""),
                })
        return results[:n]
    except:
        return []

def download_bgm(url, dest_path):
    """BGM 파일 다운로드"""
    try:
        r = requests.get(url, stream=True, timeout=30,
                         headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
            return os.path.getsize(dest_path) > 1000
    except:
        pass
    return False

# ── 썸네일 생성 헬퍼 ─────────────────────────────────────────────
def _load_pillow_font(size=60):
    """Pillow용 한글 폰트 로드 (실패 시 기본 폰트, 한글 깨짐 경고)"""
    fontpath = find_korean_font()
    if fontpath:
        try:
            return ImageFont.truetype(fontpath, size)
        except:
            pass
    # 한글 폰트 없음 → 대체 폰트 시도 (한글 글리프 없을 수 있음)
    for fb in ["arial.ttf", "Arial.ttf",
               "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
               "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
        try:
            return ImageFont.truetype(fb, size)
        except:
            continue
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()

def _draw_outlined_text(draw, pos, text, font, fill=(255,255,255), outline=(0,0,0), width=2):
    """텍스트에 외곽선 효과"""
    x, y = pos
    for dx, dy in [(-width,0),(width,0),(0,-width),(0,width),
                   (-width,-width),(width,-width),(-width,width),(width,width)]:
        draw.multiline_text((x+dx, y+dy), text, fill=outline, font=font, align="center")
    draw.multiline_text((x, y), text, fill=fill, font=font, align="center")

def _get_first_product_image():
    """제품 이미지 로컬 경로 반환 (업로드 > 추출 > None)"""
    for p in st.session_state.get("uploaded_images", []):
        if os.path.exists(p):
            return p
    prod_imgs = st.session_state.get("product_images", [])
    if prod_imgs:
        tmp = _ensure_dir("thumb_prod_img")
        dest = tmp / "prod_thumb.jpg"
        if dest.exists() and os.path.getsize(str(dest)) > 500:
            return str(dest)
        url = prod_imgs[0].get("url", "")
        if url and download_image(url, str(dest)):
            return str(dest)
    return None

def generate_thumbnail(template, resolution, main_text, sub_text="", product_img_path=None):
    """Pillow로 썸네일 생성 (임팩트형/가격강조형/문제해결형). 한글 폰트 없으면 경고 반환."""
    try:
        w, h = resolution
        tmp = _ensure_dir("shortform_thumbnails")
        tmpl_tag = {"임팩트형":"impact","가격강조형":"price","문제해결형":"solution"}.get(template,"thumb")
        out_path = tmp / f"thumb_{tmpl_tag}_{w}x{h}.png"

        # 한글 폰트 가용성 사전 체크
        _korean_font_ok = find_korean_font() is not None

        font_main = _load_pillow_font(int(min(w,h)*0.08))
        font_sub = _load_pillow_font(int(min(w,h)*0.045))
        font_badge = _load_pillow_font(int(min(w,h)*0.035))

        # 긴 텍스트 자동 줄바꿈 (14자 기준)
        if len(main_text) > 14:
            mid = len(main_text) // 2
            sp = main_text.rfind(" ", max(0, mid-5), mid+5)
            if sp > 2:
                main_text = main_text[:sp] + "\n" + main_text[sp+1:]
            else:
                main_text = main_text[:mid] + "\n" + main_text[mid:]

        # 제품 이미지 로드
        prod = None
        if product_img_path and os.path.exists(product_img_path):
            try:
                prod = Image.open(product_img_path).convert("RGBA")
            except:
                pass

        # ── 임팩트형: 어두운 배경 + 제품 중앙 + 큰 텍스트 ──
        if template == "임팩트형":
            img = Image.new("RGB", (w, h), (20, 20, 35))
            draw = ImageDraw.Draw(img)
            for y in range(h):
                rv = int(15+20*(y/h)); gv = int(15+15*(y/h)); bv = int(30+30*(y/h))
                draw.line([(0,y),(w,y)], fill=(rv,gv,bv))

            if prod:
                sz = int(min(w,h)*0.5)
                prod.thumbnail((sz,sz), Image.LANCZOS)
                img.paste(prod, ((w-prod.width)//2, int(h*0.15)), prod)
                draw = ImageDraw.Draw(img)

            bbox = draw.multiline_textbbox((0,0), main_text, font=font_main, align="center")
            tw, th_t = bbox[2]-bbox[0], bbox[3]-bbox[1]
            tx, ty = (w-tw)//2, int(h*0.72)
            _draw_outlined_text(draw, (tx,ty), main_text, font_main)

            if sub_text:
                sb = draw.multiline_textbbox((0,0), sub_text, font=font_sub, align="center")
                draw.multiline_text(((w-(sb[2]-sb[0]))//2, ty+th_t+12), sub_text,
                                    fill=(200,200,210), font=font_sub, align="center")
            try:
                draw.rounded_rectangle([int(w*0.03),int(h*0.04),int(w*0.20),int(h*0.11)], radius=10, fill=(244,67,54))
            except:
                draw.rectangle([int(w*0.03),int(h*0.04),int(w*0.20),int(h*0.11)], fill=(244,67,54))
            draw.text((int(w*0.05),int(h*0.055)), "BEST PICK", fill=(255,255,255), font=font_badge)

        # ── 가격강조형: 주황 배경 + 가격 크게 ──
        elif template == "가격강조형":
            img = Image.new("RGB", (w, h), (255,107,53))
            draw = ImageDraw.Draw(img)
            for y in range(h):
                gv = max(0, int(107-50*(y/h))); bv = max(0, int(53-30*(y/h)))
                draw.line([(0,y),(w,y)], fill=(255,gv,bv))

            if prod:
                sz = int(min(w,h)*0.45)
                prod.thumbnail((sz,sz), Image.LANCZOS)
                img.paste(prod, (int(w*0.05),(h-prod.height)//2), prod)
                draw = ImageDraw.Draw(img)

            font_price = _load_pillow_font(int(min(w,h)*0.11))
            bbox = draw.multiline_textbbox((0,0), main_text, font=font_price, align="center")
            tw, th_t = bbox[2]-bbox[0], bbox[3]-bbox[1]
            tx = max(int(w*0.50), w-tw-int(w*0.05))
            ty = int(h*0.30)
            _draw_outlined_text(draw, (tx,ty), main_text, font_price, outline=(100,0,0))

            if sub_text:
                sb = draw.multiline_textbbox((0,0), sub_text, font=font_sub, align="center")
                stw = sb[2]-sb[0]
                draw.multiline_text((max(int(w*0.50),w-stw-int(w*0.05)), ty+th_t+15),
                                    sub_text, fill=(255,240,220), font=font_sub, align="center")
            try:
                draw.rounded_rectangle([int(w*0.65),int(h*0.04),int(w*0.97),int(h*0.12)], radius=10, fill=(0,0,0))
            except:
                draw.rectangle([int(w*0.65),int(h*0.04),int(w*0.97),int(h*0.12)], fill=(0,0,0))
            draw.text((int(w*0.67),int(h*0.055)), "BEST DEAL", fill=(255,200,0), font=font_badge)

        # ── 문제해결형: Before/After 분할 ──
        elif template == "문제해결형":
            img = Image.new("RGB", (w, h), (240,245,240))
            draw = ImageDraw.Draw(img)
            for x in range(w//2):
                c = int(50+30*(x/(w//2)))
                draw.line([(x,0),(x,h)], fill=(c,c,c+5))
            for x in range(w//2, w):
                ratio = (x-w//2)/(w//2)
                draw.line([(x,0),(x,h)], fill=(int(220+30*ratio),245,int(225+25*ratio)))
            draw.rectangle([w//2-2,0,w//2+2,h], fill=(255,200,0))

            if prod:
                sz = int(min(w,h)*0.4)
                prod.thumbnail((sz,sz), Image.LANCZOS)
                px = int(w*0.55)+(int(w*0.4)-prod.width)//2
                img.paste(prod, (px,(h-prod.height)//2), prod)
                draw = ImageDraw.Draw(img)

            font_label = _load_pillow_font(int(min(w,h)*0.05))
            draw.text((int(w*0.08),int(h*0.08)), "BEFORE", fill=(180,180,180), font=font_label)
            draw.text((int(w*0.58),int(h*0.08)), "AFTER", fill=(0,150,80), font=font_label)

            draw.rectangle([0,int(h*0.75),w,h], fill=(20,20,25))
            bbox = draw.multiline_textbbox((0,0), main_text, font=font_main, align="center")
            tw, th_t = bbox[2]-bbox[0], bbox[3]-bbox[1]
            tx, ty = (w-tw)//2, int(h*0.78)
            _draw_outlined_text(draw, (tx,ty), main_text, font_main)

            if sub_text:
                sb = draw.multiline_textbbox((0,0), sub_text, font=font_sub, align="center")
                draw.multiline_text(((w-(sb[2]-sb[0]))//2, ty+th_t+8), sub_text,
                                    fill=(180,220,180), font=font_sub, align="center")

        img.save(str(out_path), "PNG")
        return str(out_path) if out_path.exists() else None
    except Exception:
        return None


# ── 헤더 ──────────────────────────────────────────────────────────
st.markdown("""
<div style="padding:32px 0 8px;">
  <h1 style="font-size:1.5rem;font-weight:800;margin:0;letter-spacing:-.01em;">🎬 Shorts AI Studio <span style="font-size:.7rem;font-weight:600;color:#FF8B5B;background:rgba(255,107,53,.1);padding:3px 8px;border-radius:6px;margin-left:6px;">BETA</span></h1>
  <p style="color:#8b95a1;font-size:.95rem;margin:4px 0 0;">소스 선택 → 클립 편집 → 자막+음성 → 다운로드</p>
  <p style="color:#FF6B35;font-size:1.25rem;font-weight:700;margin:12px 0 0;text-align:center;">쿠팡 URL 하나로 → 숏폼 영상 완성 ✨</p>
</div>
""", unsafe_allow_html=True)

# ── 사이드바 ──────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🎬 Shorts AI")
    st.markdown("---")

    # 프로젝트 정보 표시 (활성 프로젝트가 있을 때)
    if st.session_state.active_project_id:
        _prj_data = project_store.get_project(st.session_state.active_project_id)
        if _prj_data:
            st.markdown(f"📁 **{_prj_data['name']}**")
            _active_tpl = TEMPLATES.get(st.session_state.active_template, {})
            if _active_tpl:
                st.caption(f"📋 {_active_tpl.get('name', '')}")
        if st.button("🏠 프로젝트 목록", key="sidebar_home", use_container_width=True):
            st.session_state.app_phase = "project_select"
            st.rerun()
        st.markdown("---")

    # STEP 네비게이션은 pipeline 단계에서만 표시
    if st.session_state.app_phase == "pipeline":
        _step_labels = ["1. 소스 선택", "2. 클립 편집", "3. 자막 + 음성", "4. 미리보기 + 다운로드"]
        _cs = st.session_state.current_step
        _sidebar_css = '<style>'
        for _si in range(4):
            if _si + 1 == _cs:
                _sidebar_css += f'[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label:nth-child({_si+1}){{background:#FF6B35!important;border-radius:8px;}} [data-testid="stSidebar"] .stRadio div[role="radiogroup"] label:nth-child({_si+1}) span{{color:#fff!important;font-weight:700!important;}}'
            elif _si + 1 < _cs:
                _sidebar_css += f'[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label:nth-child({_si+1}) span::before{{content:"✅ ";}}'
        _sidebar_css += '</style>'
        st.markdown(_sidebar_css, unsafe_allow_html=True)
        _selected_step = st.radio("제작 단계", _step_labels,
                                  index=st.session_state.current_step - 1)
        st.session_state.current_step = _step_labels.index(_selected_step) + 1
        st.markdown("---")
        with st.expander("✂️ 영상 설정", expanded=False):
            target_dur = st.slider("목표 길이(초)", 15, 60, 30, 5, key="_w_target_dur")
            crop_ratio = st.selectbox("화면 비율", ["9:16 세로형 (숏폼)", "1:1 정방형"], key="_w_crop_ratio")
        st.markdown("---")

    with st.expander("🔑 API 연결 상태"):
        for label, env in [
            ("Claude AI", "ANTHROPIC_API_KEY"),
            ("클로바 TTS", "CLOVA_TTS_CLIENT_ID"),
            ("ElevenLabs", "ELEVENLABS_API_KEY"),
            ("Pexels 검색", "PEXELS_API_KEY"),
            ("Pixabay BGM", "PIXABAY_API_KEY"),
            ("YouTube 검색", "YOUTUBE_API_KEY"),
        ]:
            ok = has_key(env)
            st.markdown(f"{'✅' if ok else '⬜'} **{label}** {'연결됨' if ok else '미연결'}")

# ── 스텝 진행 표시 (4단계 동적) — pipeline 단계에서만 ─────────────
if st.session_state.app_phase == "pipeline":
    _step_labels_prog = ["제품설정", "클립편집", "영상생성", "다운로드"]
    _step_html = '<div style="display:flex;align-items:center;justify-content:center;gap:0;padding:12px 0 16px;">'
    for _si, _slabel in enumerate(_step_labels_prog):
        _num = _si + 1
        _is_current = _num == st.session_state.current_step
        _is_done = _num < st.session_state.current_step
        if _is_current:
            _circle_bg = "#FF6B35"; _circle_fg = "#fff"; _txt_col = "#FF6B35"; _txt_weight = "700"
        elif _is_done:
            _circle_bg = "#4CAF50"; _circle_fg = "#fff"; _txt_col = "#4CAF50"; _txt_weight = "600"
        else:
            _circle_bg = "#E5E7EB"; _circle_fg = "#6B7280"; _txt_col = "#6B7280"; _txt_weight = "500"
        _step_html += (
            f'<div style="display:flex;flex-direction:column;align-items:center;min-width:70px;">'
            f'<div style="width:32px;height:32px;border-radius:50%;background:{_circle_bg};color:{_circle_fg};'
            f'display:flex;align-items:center;justify-content:center;font-size:.85rem;font-weight:700;">'
            f'{"✓" if _is_done else _num}</div>'
            f'<span style="font-size:.75rem;font-weight:{_txt_weight};color:{_txt_col};margin-top:4px;">{_slabel}</span>'
            f'</div>'
        )
        if _si < len(_step_labels_prog) - 1:
            _line_col = "#4CAF50" if _is_done else "#E5E7EB"
            _step_html += f'<div style="flex:1;height:2px;background:{_line_col};margin:0 4px;align-self:flex-start;margin-top:16px;min-width:30px;"></div>'
    _step_html += '</div>'
    st.markdown(_step_html, unsafe_allow_html=True)


# ── 이전/다음 네비 버튼 헬퍼 ──────────────────────────────────
def _render_nav_buttons():
    st.markdown("---")
    _step_names = {1: "소스", 2: "편집", 3: "AI 대본", 4: "추적+DL"}
    _curr = st.session_state.current_step
    nav_prev, _, nav_next = st.columns([1, 3, 1])
    with nav_prev:
        if _curr > 1:
            _prev_label = _step_names.get(_curr - 1, "")
            if st.button(f"← {_prev_label}", key=f"prev_{_curr}",
                          type="secondary", use_container_width=True):
                st.session_state.current_step -= 1
                st.rerun()
    with nav_next:
        if _curr < 4:
            _next_label = _step_names.get(_curr + 1, "")
            if st.button(f"{_next_label} →", key=f"next_{_curr}",
                          type="primary", use_container_width=True):
                st.session_state.current_step += 1
                st.rerun()


# ═════════════════════════════════════════════════════════════════
# render_step1: 🔍 소스 선택 (3블록 구조)
# ═════════════════════════════════════════════════════════════════
def render_step1():
    # 통합 헤더 (STEP 표시 + 부제 한 카드)
    st.markdown(
        '<div class="ux-card">'
        '<div class="ux-card-title">STEP 01 · 소스</div>'
        '<h4 style="margin:4px 0 6px;">📦 제품 정보 입력</h4>'
        '<p class="ux-sub">제품명 + 카테고리만 정확하면 나머지는 AI가 알아서 합니다</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    # ── 🧬 경쟁사 영상 DNA 추출 (USP — 다른 도구에 없음) ──
    with st.expander("🧬 잘 된 영상 URL → DNA 추출 (이렇게 만들기)"):
        st.caption("YouTube/TikTok/Instagram에서 잘 된 영상 URL을 입력하면 "
                   "Hook/구조/CTA를 분석해서 본인 상품 대본에 적용합니다.")
        _dna_url = st.text_input(
            "경쟁사 영상 URL", placeholder="https://youtube.com/shorts/...",
            key="_dna_url_input", label_visibility="collapsed",
        )
        if st.button("🧬 DNA 분석", key="btn_dna_extract"):
            with st.spinner("영상 메타 + 자막 가져오는 중..."):
                _meta = competitor_dna.fetch_video_metadata(_dna_url)
            if _meta.get("ok"):
                with st.spinner("LLM이 viral 요소 분해 중..."):
                    _dna = competitor_dna.extract_dna(_meta)
                competitor_dna.save_dna(_dna_url, _meta, _dna,
                                          st.session_state.get("coupang_product", ""))
                st.session_state["_last_dna"] = _dna
                st.session_state["_last_dna_meta"] = _meta
            else:
                st.error(f"❌ {_meta.get('error', '실패')}")

        _dna = st.session_state.get("_last_dna")
        _meta = st.session_state.get("_last_dna_meta")
        if _dna and _meta:
            st.markdown(
                f'<div style="background:rgba(255,107,53,.08);border:1px solid rgba(255,107,53,.3);'
                f'border-radius:10px;padding:12px;margin:8px 0;">'
                f'<div style="font-size:.85rem;font-weight:700;color:#FF8B5B;margin-bottom:6px;">'
                f'🧬 분석된 DNA</div>'
                f'<div style="font-size:.82rem;color:#E5E5EB;line-height:1.6;">'
                f'• Hook 패턴: <strong>{_dna.get("hook_pattern", "")}</strong><br>'
                f'• 구조: {_dna.get("structure", "")}<br>'
                f'• CTA: {_dna.get("cta_pattern", "")}<br>'
                f'• 작동 요소: {", ".join(_dna.get("viral_factors", [])[:3])}<br>'
                f'• 조회수: {_meta.get("view_count", 0):,} · 좋아요: {_meta.get("like_count", 0):,}'
                f'</div></div>',
                unsafe_allow_html=True,
            )
            st.caption("💡 STEP 3 대본 생성 시 이 DNA가 자동 적용됩니다.")

    # ── 쿠팡 앱 공유 텍스트 자동 파싱 (가장 빠른 입력 방법) ──
    st.markdown("##### 📱 쿠팡 앱 '공유' 텍스트 붙여넣기 <span style='font-size:.7rem;color:#10B981;font-weight:600;'>가장 빠름</span>",
                unsafe_allow_html=True)
    _share_text = st.text_area(
        "쿠팡 공유 텍스트",
        placeholder="쿠팡 앱 → 상품 → 공유 → 카톡/메모 등으로 보낸 텍스트 그대로 붙여넣기\n\n예시:\n[쿠팡] 닥터자르트 시카페어 토너 200ml\nhttps://link.coupang.com/a/exnTX4",
        height=80,
        label_visibility="collapsed",
        key="_share_text_input",
        help="쿠팡 앱에서 상품 페이지 → 우측 상단 공유 버튼 → 텍스트 복사 → 여기에 붙여넣기. 상품명 + URL이 자동 분리됩니다.",
    )
    _btn_parse = st.button("✨ 자동 분리하기", key="btn_parse_share",
                            use_container_width=False, type="primary")

    if _btn_parse and _share_text:
        _parsed = parse_coupang_share_text(_share_text)
        if _parsed["name"]:
            st.session_state.coupang_product = _parsed["name"]
        if _parsed["url"]:
            st.session_state["_parsed_url"] = _parsed["url"]
        if _parsed["success"]:
            st.success(f"✅ 자동 분리 완료: **{_parsed['name'] or '(상품명 없음)'}**"
                        f"{f' · URL 인식됨' if _parsed['url'] else ''}")
        else:
            st.warning("⚠️ 인식 실패 — 아래 입력란에 직접 입력해주세요.")

    st.markdown("---")
    st.markdown("##### 🛒 쿠팡 상품 URL <span style='font-size:.7rem;color:#9CA3AF;font-weight:400;'>선택 · 추적 링크용</span>",
                unsafe_allow_html=True)
    _default_url = st.session_state.pop("_parsed_url", "") if st.session_state.get("_parsed_url") else ""
    coupang_url = st.text_input(
        "쿠팡 상품 URL",
        value=_default_url,
        placeholder="https://link.coupang.com/a/XXXXX  (단축 URL도 OK)",
        label_visibility="collapsed",
        help="쿠팡 파트너스 API 없어도 동작. URL은 STEP 4 추적 링크에만 쓰임."
    )

    col_extract, col_status = st.columns([1, 3])
    with col_extract:
        do_extract = st.button("🔍 상품 정보 추출", use_container_width=True)

    if do_extract and coupang_url:
        with st.spinner("상품 정보 추출 중..."):
            og = scrape_og_tags(coupang_url) if "link.coupang.com" not in coupang_url else {}
            st.session_state["og_tags"] = og
            info = extract_coupang_info(coupang_url)

            _bad_og = ("deeplink", "redirect", "쿠팡!", "coupang")
            _og_clean = (og.get("og_title", "").strip()
                          if og.get("og_title") else "")
            _og_useless = (not _og_clean or
                            any(b in _og_clean.lower() for b in _bad_og) or
                            len(_og_clean) <= 5)

            if info["success"]:
                st.session_state.coupang_product = info["name"]
            elif _og_clean and not _og_useless:
                cleaned = _og_clean.replace(" - 쿠팡!", "").replace(" | 쿠팡", "").strip()
                st.session_state.coupang_product = cleaned
                info["success"] = True

            # ── 통합 결과 카드 (성공/실패 한 장으로) ──
            if info["success"]:
                _img_url = og.get("og_image", "")
                _desc = og.get("og_description", "")[:120]
                _img_html = ""
                if _img_url:
                    _img_html = (f'<img src="{_img_url}" style="width:80px;height:80px;'
                                  f'border-radius:8px;object-fit:cover;flex-shrink:0;" alt="">')
                _desc_html = ""
                if _desc:
                    _desc_html = (f'<div style="font-size:.82rem;color:#166534;margin-top:6px;">'
                                   f'{_desc}</div>')
                _name = st.session_state.coupang_product
                st.markdown(
                    f'<div style="background:linear-gradient(135deg,#F0FDF4 0%,#DCFCE7 100%);'
                    f'border:1px solid #86EFAC;border-radius:12px;padding:16px;margin:8px 0;'
                    f'display:flex;gap:12px;align-items:flex-start;">'
                    f'{_img_html}'
                    f'<div style="flex:1;">'
                    f'<div style="font-size:.75rem;color:#15803D;font-weight:700;'
                    f'text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px;">'
                    f'✅ 추출 완료</div>'
                    f'<div style="font-size:1rem;font-weight:700;color:#14532D;'
                    f'line-height:1.4;">{_name}</div>'
                    f'{_desc_html}'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )
            else:
                _pid = info.get("product_id", "")
                _placeholder_text = f"쿠팡 상품 #{_pid}" if _pid else ""
                if _pid and not st.session_state.coupang_product:
                    st.session_state.coupang_product = _placeholder_text
                _pid_html = ""
                if _pid:
                    _pid_html = (f'<br><span style="opacity:.7;font-size:.78rem;">'
                                  f'URL에서 자동 감지: 쿠팡 상품 ID #{_pid}</span>')
                # 통합 단일 카드 — warning + 안내 + 사유 한 번에
                st.markdown(
                    f'<div style="background:linear-gradient(135deg,#FFFBEB 0%,#FEF3C7 100%);'
                    f'border:1px solid #FCD34D;border-radius:12px;padding:16px;margin:8px 0;">'
                    f'<div style="font-size:.95rem;font-weight:700;color:#92400E;'
                    f'margin-bottom:8px;">ℹ️ 자동 추출 불가 — 상품명만 직접 입력하면 됩니다</div>'
                    f'<div style="font-size:.85rem;color:#78350F;line-height:1.5;">'
                    f'쿠팡은 모든 외부 도구를 차단합니다 (정책). '
                    f'<strong>📱 쿠팡 앱에서 상품명 복사 → 아래 입력란에 붙여넣기</strong> 만 하시면 '
                    f'AI 대본 + 추적 링크 모든 기능 정상 작동합니다.'
                    f'{_pid_html}'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )

    # ── OG 결과 표시 (이전 추출 결과) ──
    if st.session_state.get("og_tags", {}).get("success") and not do_extract:
        og = st.session_state["og_tags"]
        with st.expander("🏷️ OG 태그 추출 결과", expanded=False):
            if og.get("og_image"):
                st.image(og["og_image"], width=200)
            if og.get("og_title"):
                st.markdown(f"**제목**: {og['og_title']}")
            if og.get("og_description"):
                st.markdown(f"**설명**: {og['og_description'][:150]}")

    # ── 제품명 (단일화 — 기존 2개 제품명 입력란 통합) ──
    st.markdown("##### ✏️ 제품명 <span style='color:#EF4444;'>*</span>",
                unsafe_allow_html=True)
    st.session_state.coupang_product = st.text_input(
        "제품명",
        value=st.session_state.coupang_product,
        placeholder="예: 닥터자르트 시카페어 토너 200ml",
        label_visibility="collapsed",
        help="쿠팡 앱에서 상품명 그대로 복사해 붙여넣으면 가장 좋아요.",
    )

    # ── 카테고리 자동 추론 + 강조 ──
    _ui_categories = ["전자기기", "뷰티/화장품", "패션/의류", "식품",
                       "생활용품", "건강/헬스", "유아/키즈", "반려동물", "기타"]
    _name_for_infer = st.session_state.coupang_product or ""
    _suggested_cat = ""
    if _name_for_infer:
        try:
            _internal_id = category_templates.infer_category(_name_for_infer)
            _id_to_ui = {v: k for k, v in
                          category_templates.UI_TO_INTERNAL_CATEGORY.items()}
            _suggested_cat = _id_to_ui.get(_internal_id, "")
        except Exception:
            pass
    _curr_cat = st.session_state.coupang_category or _suggested_cat or "기타"
    _default_idx = _ui_categories.index(_curr_cat) if _curr_cat in _ui_categories else 0

    st.markdown("##### 🏷️ 카테고리 <span style='color:#EF4444;'>*</span>",
                unsafe_allow_html=True)
    if (_suggested_cat and _suggested_cat != "기타"
            and _suggested_cat != st.session_state.coupang_category):
        st.markdown(
            f'<div style="background:#FFF7ED;border-left:3px solid #FF6B35;'
            f'padding:8px 12px;border-radius:6px;margin-bottom:6px;'
            f'font-size:.85rem;color:#9A3412;">'
            f'💡 제품명 분석 → <strong>{_suggested_cat}</strong> 카테고리 추천. '
            f'아래에서 변경하세요.'
            f'</div>',
            unsafe_allow_html=True,
        )
    st.session_state.coupang_category = st.selectbox(
        "카테고리",
        _ui_categories,
        index=_default_idx,
        label_visibility="collapsed",
        help="카테고리에 맞는 viral 패턴/Hook/CTA가 자동 적용돼요.",
    )

    # ── 제품 설명 (선택, 접기 — 진입 부담 낮춤) ──
    with st.expander("📝 제품 설명 추가 (선택, 대본 품질 ↑)"):
        product_desc = st.text_area(
            "특징/장점",
            placeholder="예: 시카 성분 70% 농도, 200ml 대용량, 민감성 피부 진정",
            height=85, key="_w_pdesc",
            label_visibility="collapsed",
        )
        if product_desc:
            st.session_state["_saved_pdesc"] = product_desc

    if st.session_state.coupang_product:
        st.session_state["_saved_pname"] = st.session_state.coupang_product
    product_name = st.session_state.coupang_product

    content_modes = ["클릭유도형", "구매전환형", "리뷰형", "비교형", "문제해결형", "바이럴형"]
    mode_desc = {
        "클릭유도형": "궁금증·충격으로 클릭 유도",
        "구매전환형": "구매 결정을 촉진",
        "리뷰형": "사용 후기·장단점 중심",
        "비교형": "경쟁 제품과 비교 분석",
        "문제해결형": "문제 제시 → 해결",
        "바이럴형": "공유·밈·감성 자극",
    }
    st.session_state.content_mode = st.selectbox(
        "🎯 콘텐츠 목적",
        content_modes,
        index=content_modes.index(st.session_state.content_mode) if st.session_state.content_mode in content_modes else 0,
        help="콘텐츠 목적에 따라 AI가 제목·스크립트·해시태그 스타일을 맞춰줍니다."
    )
    st.caption(f"💡 {mode_desc.get(st.session_state.content_mode, '')}")
    st.markdown("---")
    st.markdown("**🔗 쿠팡 제휴 링크**")
    st.session_state.coupang_affiliate_link = st.text_input(
        "제휴 링크 URL",
        value=st.session_state.coupang_affiliate_link,
        placeholder="https://link.coupang.com/...",
        help="유튜브/인스타 설명란에 자동 삽입됩니다.",
        label_visibility="collapsed"
    )
    if st.session_state.coupang_affiliate_link:
        st.markdown('<span class="badge badge-green">✓ 링크 등록됨</span>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # ── 제품 이미지 (썸네일/오버레이용) ──
    st.markdown("#### 🖼️ 제품 이미지 (썸네일/오버레이용)")
    st.caption("제품 이미지는 자막 오버레이 및 썸네일 생성에 활용됩니다.")
    uploaded_imgs = st.file_uploader("이미지 업로드 (여러 개 가능)", type=["jpg", "jpeg", "png", "webp"], accept_multiple_files=True, key="img_uploader")
    if uploaded_imgs:
        img_dir = _ensure_dir("uploaded_images")
        local_paths = []
        up_cols = st.columns(min(len(uploaded_imgs), 4))
        for i, f in enumerate(uploaded_imgs):
            dest = img_dir / f.name
            dest.write_bytes(f.read())
            local_paths.append(str(dest))
            with up_cols[i % len(up_cols)]:
                try:
                    st.image(str(dest), use_container_width=True)
                except:
                    st.caption(f.name)
        st.session_state.uploaded_images = local_paths
        st.success(f"✅ {len(local_paths)}개 제품 이미지 등록됨 (썸네일/오버레이용)")
        # # ── Ken Burns 영상 변환 (비활성 — 나중에 재활용 가능) ──
        # kb_dur_b = st.slider("이미지당 시간 (초)", 2, 4, 3, key="kb_dur_b")
        # if st.button("🎬 Ken Burns 영상 생성", key="kb_gen_b", use_container_width=True):
        #     with st.spinner("Ken Burns 효과 적용 중..."):
        #         out_path, err = images_to_kenburns_video(local_paths, kb_dur_b)
        #         if out_path:
        #             dur = get_video_duration(out_path)
        #             st.session_state.clips.append({
        #                 "name": f"업로드이미지_kenburns.mp4",
        #                 "path": out_path,
        #                 "duration": f"{int(dur//60)}:{int(dur%60):02d}",
        #                 "dur_sec": dur,
        #                 "source": "kenburns",
        #             })
        #             st.success(f"✅ Ken Burns 영상 생성 완료! ({dur:.0f}초) → STEP 2 클립에 자동 추가됨")
        #             st.video(out_path)
        #         else:
        #             st.error(f"❌ 영상 생성 실패: {err}")

    # ── 쿠팡 URL / 제품명 / 카테고리 변경 감지 → 검색 상태 reset ──
    _current_url = coupang_url
    _current_product = st.session_state.coupang_product
    _current_cat = st.session_state.coupang_category
    _prev_key = f"{st.session_state.get('_last_coupang_url', '')}|{st.session_state.get('_last_product', '')}|{st.session_state.get('_last_category', '')}"
    _curr_key = f"{_current_url}|{_current_product}|{_current_cat}"
    if _prev_key != _curr_key and (_current_url or _current_product):
        st.session_state._last_coupang_url = _current_url
        st.session_state._last_product = _current_product
        st.session_state._last_category = _current_cat
        st.session_state.pexels_searched = False
        st.session_state.pexels_results = []
        st.session_state.youtube_results = []
        st.session_state.instagram_links = []
        st.session_state.pexels_ai_keywords = []

    # ╔══════════════════════════════════════════════════════════╗
    # ║ 블록 2: 🎬 영상 확보                                      ║
    # ╚══════════════════════════════════════════════════════════╝
    st.markdown("## 🎬 블록 2 — 영상 확보")

    # ═══════ 추천 영상 찾기 (7차) ═══════
    _rec_pn = (st.session_state.get("_w_pname", "") or st.session_state.get("_saved_pname", "") or st.session_state.coupang_product or "")
    with st.expander("🔎 추천 영상 찾기 (YouTube)", expanded=False):
        st.markdown('<div class="info-box">제품명 기반으로 YouTube에서 참고할 숏폼 영상을 자동 검색합니다. 선택하면 자동 다운로드 &rarr; 클립 분할 &rarr; STEP 2로 이동합니다.</div>', unsafe_allow_html=True)
        if not _rec_pn:
            st.warning("위 블록 1에서 제품명을 먼저 입력해주세요.")
        else:
            _rec_kw_col, _rec_btn_col = st.columns([3, 1])
            with _rec_btn_col:
                _rec_do_search = st.button("🔍 추천 영상 검색", key="rec_search_btn", type="primary", use_container_width=True)
            with _rec_kw_col:
                if st.session_state.recommended_keywords:
                    st.markdown(f"**검색 키워드:** {' · '.join(st.session_state.recommended_keywords)}")
            if _rec_do_search:
                with st.spinner("AI 키워드 생성 + YouTube 검색 중..."):
                    _rec_cat = st.session_state.coupang_category or "기타"
                    _rec_kws = generate_youtube_keywords(_rec_pn, _rec_cat)
                    st.session_state.recommended_keywords = _rec_kws
                    _rec_vids = search_youtube_recommendations(_rec_kws, max_results=5)
                    st.session_state.recommended_videos = _rec_vids
                    if _rec_vids:
                        st.success(f"✅ {len(_rec_vids)}개 추천 영상을 찾았습니다!")
                    else:
                        st.warning("검색 결과가 없습니다. 제품명을 변경해보세요.")
                st.rerun()
            # 결과 표시
            if st.session_state.recommended_videos:
                st.markdown("---")
                _rec_ncols = min(len(st.session_state.recommended_videos), 3)
                _rec_cols = st.columns(_rec_ncols)
                for _ri, _rv in enumerate(st.session_state.recommended_videos):
                    with _rec_cols[_ri % _rec_ncols]:
                        if _rv.get("thumbnail"):
                            try:
                                st.image(_rv["thumbnail"], use_container_width=True)
                            except Exception:
                                pass
                        _short_tag = " 🎬Shorts" if _rv.get("is_short") else ""
                        st.markdown(f"**{_rv['title'][:40]}**{_short_tag}")
                        st.caption(f"📺 {_rv['channel']} · ⏱ {_rv['duration']} · 👀 {_rv.get('views', '')}")
                        if st.button("✅ 이 영상 사용", key=f"rec_use_{_ri}", use_container_width=True, type="primary"):
                            with st.spinner(f"다운로드 + 클립 분할 중..."):
                                _rec_fpath, _rec_err = download_video_with_fallback(_rv["url"])
                                if _rec_fpath:
                                    import clip_analyzer as _ca
                                    _rec_ts = _ca.analyze_scenes(_rec_fpath)
                                    _rec_clips = _ca.split_clips(_rec_fpath, _rec_ts)
                                    if _rec_clips:
                                        _tag_order = ["인트로", "사용장면", "사용장면", "아웃트로"]
                                        for _ci, _cl in enumerate(_rec_clips):
                                            _cl["usage_tag"] = _tag_order[min(_ci, len(_tag_order)-1)]
                                            _cl["source"] = "youtube_rec"
                                        st.session_state.clips.extend(_rec_clips)
                                        st.session_state.selected_recommended_video = _rv
                                        st.success(f"✅ {len(_rec_clips)}개 클립 추가 완료! STEP 2로 이동합니다.")
                                        st.session_state.current_step = 2
                                        st.rerun()
                                    else:
                                        _dur_str = _rv.get("duration", "0:00")
                                        st.session_state.clips.append({
                                            "name": os.path.basename(_rec_fpath), "path": _rec_fpath,
                                            "duration": _dur_str, "dur_sec": _rv.get("dur_sec", 0),
                                            "source": "youtube_rec", "usage_tag": "사용장면",
                                        })
                                        st.session_state.selected_recommended_video = _rv
                                        st.success("✅ 영상 추가 완료! STEP 2로 이동합니다.")
                                        st.session_state.current_step = 2
                                        st.rerun()
                                else:
                                    st.error(f"다운로드에 실패했습니다. 직접 업로드해주세요. ({_rec_err or ''})")
                        st.link_button("🔗 YouTube에서 보기", _rv["url"], use_container_width=True)

    _src_opts = ["🌐 외부 URL 다운로드 (yt-dlp)", "🎬 Pexels 배경 영상", "🎥 영상 직접 업로드"]
    _src_map = {"🌐 외부 URL 다운로드 (yt-dlp)": "URL", "🎬 Pexels 배경 영상": "이미지", "🎥 영상 직접 업로드": "영상"}
    _src_reverse = {"URL": "🌐 외부 URL 다운로드 (yt-dlp)", "이미지": "🎬 Pexels 배경 영상", "영상": "🎥 영상 직접 업로드"}
    _cur_src_label = _src_reverse.get(st.session_state.source_type, "🌐 외부 URL 다운로드 (yt-dlp)")
    _src_sel = st.radio("영상 확보 방법", _src_opts, horizontal=True, key="source_type_radio",
                        index=_src_opts.index(_cur_src_label) if _cur_src_label in _src_opts else 0)
    st.session_state.source_type = _src_map[_src_sel]

    # ═══════ A) 외부 URL 다운로드 (yt-dlp) ═══════
    if st.session_state.source_type == "URL":
        st.markdown("### 🌐 외부 영상 다운로드 (yt-dlp)")
        st.markdown('<div class="info-box">더우인(Douyin), 틱톡, 유튜브, 인스타 등의 영상 URL을 입력하면 자동 다운로드합니다. (최대 100MB)</div>', unsafe_allow_html=True)
        with st.expander("📋 지원 URL 예시", expanded=False):
            st.markdown("""
✅ `https://www.douyin.com/video/7xxxxxxxxxx`
✅ `https://v.douyin.com/xxxxxxx/` (단축 URL)
✅ `https://www.tiktok.com/@user/video/7xxxxxxxxxx`
✅ `https://youtube.com/shorts/xxxxxxxxxxx`
✅ `https://www.youtube.com/watch?v=xxxxxxxxxxx`
✅ `https://www.instagram.com/reel/xxxxxxxxxxx/`
✅ `https://x.com/user/status/xxxxxxxxxxx` (트위터)
❌ 구글, 쿠팡, 네이버 등 일반 웹 URL 불가
❌ 로그인 필요한 비공개 영상 불가
""")

        _ytdlp_url = st.text_input(
            "영상 URL 입력",
            placeholder="https://www.douyin.com/video/... 또는 https://www.tiktok.com/... 또는 YouTube URL",
            key="_ytdlp_url_input"
        )

        _ytdlp_c1, _ytdlp_c2 = st.columns([1, 3])
        with _ytdlp_c1:
            _ytdlp_btn = st.button("⬇️ 다운로드", key="ytdlp_download_btn", use_container_width=True, type="primary")

        if _ytdlp_btn and _ytdlp_url:
            with st.spinner("영상 다운로드 중... (yt-dlp → scraper fallback, 최대 5분)"):
                fpath, err = download_video_with_fallback(_ytdlp_url)
                if fpath:
                    dur = get_video_duration(fpath)
                    fname = os.path.basename(fpath)
                    dur_str = f"{int(dur//60)}:{int(dur%60):02d}" if dur else "--:--"
                    # 중복 방지
                    if fname not in [c["name"] for c in st.session_state.clips]:
                        st.session_state.clips.append({
                            "name": fname,
                            "path": fpath,
                            "duration": dur_str,
                            "dur_sec": dur,
                            "source": "ytdlp",
                        })
                    fsize_mb = os.path.getsize(fpath) / (1024 * 1024)
                    st.success(f"✅ 다운로드 완료! ({fsize_mb:.1f}MB, {dur_str}) → STEP 2에서 편집")
                    st.video(fpath)
                else:
                    st.error(f"❌ {err}")

        st.caption("⚠️ 다운로드 실패 시, 브라우저에서 영상을 직접 저장 → **C) 영상 직접 업로드**를 이용하세요.")

        # 더우인 바로가기 링크
        st.markdown("---")
        _douyin_kw = st.session_state.get("coupang_product", "") or st.session_state.get("_w_pname", "") or st.session_state.get("_saved_pname", "")
        if _douyin_kw:
            _douyin_url = f"https://www.douyin.com/search/{_douyin_kw}"
        else:
            _douyin_url = "https://www.douyin.com"
        st.markdown("#### 🎵 더우인(Douyin) 바로가기")
        st.caption("더우인에서 제품 관련 영상을 찾고, URL을 위에 붙여넣어 다운로드하세요.")
        _dy_c1, _dy_c2 = st.columns(2)
        with _dy_c1:
            st.link_button("🔗 더우인에서 검색", _douyin_url)
        with _dy_c2:
            st.text_input("복사용 링크", _douyin_url, key="douyin_copy_url", label_visibility="collapsed")

        # 쿠팡 제품 이미지/동영상 자동 추출 (기존 기능 유지)
        if coupang_url:
            st.markdown("---")
            st.markdown("### 🛒 제품 이미지 자동 추출")
            st.markdown('<div class="info-box">상품 URL에서 제품 이미지를 추출 → Ken Burns 영상화</div>', unsafe_allow_html=True)
            if st.button("📸 이미지 추출하기", key="extract_imgs_coupang"):
                with st.spinner("제품 이미지 추출 중..."):
                    imgs = extract_product_images(coupang_url)
                    if imgs:
                        st.session_state.product_images = imgs
                        st.success(f"✅ {len(imgs)}개 이미지 추출 완료!")
                    else:
                        st.warning("이미지 추출 실패 — 쿠팡의 봇 차단 정책 때문일 수 있어요.")

            if st.session_state.product_images:
                st.markdown(f"**추출된 이미지 ({len(st.session_state.product_images)}개)**")
                img_rows = [st.session_state.product_images[i:i+4] for i in range(0, len(st.session_state.product_images), 4)]
                for row in img_rows:
                    img_cols = st.columns(4)
                    for col, img in zip(img_cols, row):
                        with col:
                            try:
                                st.image(img["url"], use_container_width=True)
                            except:
                                st.markdown('<div style="background:#f7f8fa;height:80px;border-radius:8px;display:flex;align-items:center;justify-content:center;">🖼️</div>', unsafe_allow_html=True)
                            st.caption(img.get("alt", "")[:20])

                kb_dur = st.slider("이미지당 시간 (초)", 2, 4, 3, key="kb_dur_a")
                if st.button("🎬 Ken Burns 영상 생성", key="kb_gen_a", use_container_width=True):
                    with st.spinner("이미지 다운로드 + Ken Burns 효과 적용 중..."):
                        img_dir = _ensure_dir("product_images")
                        local_paths = []
                        for i, img in enumerate(st.session_state.product_images):
                            dest = img_dir / f"prod_{i}.jpg"
                            if download_image(img["url"], str(dest)):
                                local_paths.append(str(dest))
                        if local_paths:
                            out_path, err = images_to_kenburns_video(local_paths, kb_dur)
                            if out_path:
                                dur = get_video_duration(out_path)
                                st.session_state.clips.append({
                                    "name": f"제품이미지_kenburns.mp4",
                                    "path": out_path,
                                    "duration": f"{int(dur//60)}:{int(dur%60):02d}",
                                    "dur_sec": dur,
                                    "source": "kenburns",
                                })
                                st.success(f"✅ Ken Burns 영상 생성 완료! ({dur:.0f}초) → STEP 2 클립에 자동 추가됨")
                                st.video(out_path)
                            else:
                                st.error(f"❌ 영상 생성 실패: {err}")
                        else:
                            st.error("이미지 다운로드 실패")

            st.markdown("---")
            # 제품 동영상 자동 추출
            st.markdown("### 🛒 제품 동영상 자동 추출")
            st.markdown('<div class="info-box">쿠팡 상품 페이지에서 제품 소개 동영상을 자동 추출합니다.</div>', unsafe_allow_html=True)
            if st.button("🎥 제품 동영상 추출", key="extract_prod_videos", use_container_width=True):
                with st.spinner("제품 동영상 URL 추출 중..."):
                    prod_videos = extract_product_videos(coupang_url)
                    if prod_videos:
                        st.session_state["_prod_videos"] = prod_videos
                        st.success(f"✅ {len(prod_videos)}개 제품 동영상 발견!")
                    else:
                        st.warning("동영상을 찾지 못했어요. 이미지 추출 또는 직접 업로드를 이용하세요.")

            if st.session_state.get("_prod_videos"):
                for vi, pv in enumerate(st.session_state["_prod_videos"]):
                    pv_col1, pv_col2 = st.columns([4, 1])
                    with pv_col1:
                        st.code(pv["url"][:80] + ("..." if len(pv["url"]) > 80 else ""), language=None)
                    with pv_col2:
                        already_added = any(c.get("name", "").startswith(f"제품동영상_{vi}") for c in st.session_state.clips)
                        if already_added:
                            st.markdown("<span class='badge badge-green'>✓ 추가됨</span>", unsafe_allow_html=True)
                        elif st.button(f"＋ 클립 추가", key=f"add_pvid_{vi}", use_container_width=True):
                            save_dir = _ensure_dir("shortform_clips")
                            dest = save_dir / f"product_video_{vi}.mp4"
                            with st.spinner("동영상 다운로드 중..."):
                                if download_video(pv["url"], str(dest)):
                                    dur = get_video_duration(str(dest))
                                    st.session_state.clips.append({
                                        "name": f"제품동영상_{vi}.mp4",
                                        "path": str(dest),
                                        "duration": f"{int(dur//60)}:{int(dur%60):02d}",
                                        "dur_sec": dur,
                                        "source": "product",
                                    })
                                    st.success("✅ 클립에 추가됨!")
                                    st.rerun()
                                else:
                                    st.error("다운로드 실패 — URL이 만료되었을 수 있어요")

    # ═══════ B) Pexels 배경 영상 검색 ═══════
    elif st.session_state.source_type == "이미지":
        st.markdown("### 🎬 Pexels 배경 영상 검색")
        if not has_key("PEXELS_API_KEY"):
            st.markdown('<div class="demo-banner">⚠️ PEXELS_API_KEY 필요 — Secrets에 등록하세요</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="info-box">직접 키워드를 입력하거나, AI 추천 키워드를 클릭해 검색하세요. (영어 키워드 권장)</div>', unsafe_allow_html=True)

            # AI 추천 키워드
            _ai_pname_b2 = st.session_state.get("_w_pname", "") or st.session_state.get("_saved_pname", "") or st.session_state.coupang_product or ""
            if has_key("ANTHROPIC_API_KEY") and _ai_pname_b2:
                if st.button("🤖 AI 추천 키워드 생성", key="ai_pexels_kw_btn_b2", use_container_width=True):
                    with st.spinner("AI가 Pexels 검색 키워드를 추천 중..."):
                        _kw_result = call_claude(
                            "Pexels 스톡 영상 검색 전문가. 제품과 직접 관련된 영어 키워드만 출력. 반드시 제품 자체를 촬영한 영상을 찾을 수 있는 키워드 위주.",
                            f"제품: {_ai_pname_b2}\n카테고리: {st.session_state.coupang_category or '기타'}\n\n"
                            "이 제품을 직접 보여주는 Pexels 스톡 영상 검색 키워드 5개를 추천해줘.\n"
                            "규칙:\n"
                            "1. 반드시 제품명/제품 종류를 키워드에 포함할 것\n"
                            "2. 'minimal background', 'lifestyle aesthetic' 같은 추상적 키워드 금지\n"
                            "3. 각 키워드는 영어 2~4단어, 한 줄에 하나씩, 번호 없이 출력\n"
                            "예시 (아이폰인 경우):\niphone closeup\nsmartphone screen\nphone unboxing hand\nmobile app screen\niphone camera test",
                            max_tokens=200
                        )
                        if _kw_result:
                            _keywords = [line.strip() for line in _kw_result.strip().split("\n") if line.strip() and not line.strip().startswith("#")]
                            st.session_state.pexels_ai_keywords = _keywords[:5]
                            st.success(f"✅ {len(st.session_state.pexels_ai_keywords)}개 추천 키워드 생성!")

            # 추천 키워드 버튼
            if st.session_state.get("pexels_ai_keywords"):
                st.markdown("**🤖 AI 추천 키워드** (클릭하면 자동 검색):")
                _ai_kw_cols_b2 = st.columns(min(len(st.session_state.pexels_ai_keywords), 5))
                _clicked_ai_kw_b2 = None
                for ki, _kw_item in enumerate(st.session_state.pexels_ai_keywords):
                    with _ai_kw_cols_b2[ki % len(_ai_kw_cols_b2)]:
                        if st.button(f"🔍 {_kw_item}", key=f"ai_kw_b2_{ki}", use_container_width=True):
                            _clicked_ai_kw_b2 = _kw_item
                if _clicked_ai_kw_b2:
                    with st.spinner(f"'{_clicked_ai_kw_b2}' 검색 중..."):
                        st.session_state.pexels_results = search_pexels(_clicked_ai_kw_b2, 9)
                    if st.session_state.pexels_results:
                        st.success(f"✅ '{_clicked_ai_kw_b2}' — {len(st.session_state.pexels_results)}개 영상 발견!")
                    else:
                        st.warning("결과 없음. 다른 키워드를 시도해보세요.")

            # 직접 키워드 검색
            st.markdown("---")
            px_c1, px_c2, px_c3 = st.columns([3, 1, 1])
            with px_c1:
                px_kw = st.text_input("키워드 직접 입력 (영어 권장)", placeholder="예: product showcase, minimal background", label_visibility="collapsed", key="kw_input_b2")
            with px_c2:
                px_n = st.selectbox("개수", [9, 12, 15], index=1, label_visibility="collapsed", key="px_n_b2")
            with px_c3:
                px_search = st.button("🔍 검색", use_container_width=True, key="px_search_b2")
            if px_search and px_kw:
                with st.spinner(f"'{px_kw}' 검색 중..."):
                    st.session_state.pexels_results = search_pexels(px_kw, px_n)
                if st.session_state.pexels_results:
                    st.success(f"✅ {len(st.session_state.pexels_results)}개 배경 영상 발견!")
                else:
                    st.warning("결과 없음. 다른 키워드를 시도해보세요.")

        # Pexels 결과 그리드 표시
        if st.session_state.pexels_results:
            results = st.session_state.pexels_results
            rows = [results[i:i+3] for i in range(0, len(results), 3)]
            for row in rows:
                cols = st.columns(3)
                for col, v in zip(cols, row):
                    with col:
                        if v.get("thumbnail"):
                            try:
                                st.image(v["thumbnail"], use_container_width=True)
                            except:
                                st.markdown('<div style="background:#f7f8fa;height:120px;border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:2rem;">🎬</div>', unsafe_allow_html=True)
                        st.markdown(f"**{v['title'][:30]}**")
                        st.caption(f"⏱ {v['duration']} · 👤 {v['author']}")
                        vid_id = str(v["id"])
                        already = any(c.get("search_id") == vid_id for c in st.session_state.clips)
                        if already:
                            st.markdown("<span class='badge badge-green'>✓ 추가됨</span>", unsafe_allow_html=True)
                        else:
                            px_role = st.selectbox("용도", ["배경", "인트로", "아웃트로"], key=f"role_b2_{vid_id}", label_visibility="collapsed")
                            if st.button(f"＋ {px_role}로 추가", key=f"add_b2_{vid_id}", use_container_width=True):
                                save_dir = _ensure_dir("shortform_clips")
                                dest = save_dir / f"pexels_{vid_id}.mp4"
                                with st.spinner("영상 다운로드 중..."):
                                    if v.get("download_url") and download_video(v["download_url"], str(dest)):
                                        dur = get_video_duration(str(dest))
                                        st.session_state.clips.append({
                                            "name": f"[{px_role}] pexels_{vid_id}.mp4",
                                            "path": str(dest),
                                            "duration": f"{int(dur//60)}:{int(dur%60):02d}",
                                            "dur_sec": dur,
                                            "search_id": vid_id,
                                            "source": "pexels",
                                        })
                                        st.rerun()
                                    else:
                                        st.error("다운로드 실패")

    # ═══════ C) 영상 직접 업로드 ═══════
    elif st.session_state.source_type == "영상":
        st.markdown("### 🎥 영상 직접 업로드")
        st.markdown('<div class="info-box">내 영상 파일을 직접 업로드해 클립에 추가합니다. (mp4, mov, avi, webm 지원)</div>', unsafe_allow_html=True)
        st.info("💡 타오바오/알리/더우인 등에서 확보한 제품 홍보 영상을 여기에 업로드하세요.")

        uploaded_vids = st.file_uploader(
            "영상 파일 업로드 (여러 개 가능)",
            type=["mp4", "mov", "avi", "webm"],
            accept_multiple_files=True,
            key="vid_uploader_step1",
        )
        if uploaded_vids:
            save_dir = _ensure_dir("shortform_clips")
            added_count = 0
            for vf in uploaded_vids:
                dest = save_dir / vf.name
                dest.write_bytes(vf.read())
                dur = get_video_duration(str(dest))
                dur_str = f"{int(dur//60)}:{int(dur%60):02d}" if dur else "--:--"
                # 중복 방지
                if vf.name not in [c["name"] for c in st.session_state.clips]:
                    st.session_state.clips.append({
                        "name": vf.name,
                        "path": str(dest),
                        "duration": dur_str,
                        "dur_sec": dur,
                        "source": "upload",
                    })
                    added_count += 1
            if added_count:
                st.success(f"✅ {added_count}개 영상이 클립에 추가됨! → STEP 2에서 순서 편집 가능")
            else:
                st.info("이미 추가된 영상입니다.")

            # 업로드된 영상 미리보기
            for vf in uploaded_vids:
                dest = save_dir / vf.name
                if dest.exists():
                    with st.expander(f"🎬 {vf.name}"):
                        st.video(str(dest))

        # ── 자동 클립 분할 ──
        st.markdown("---")
        st.markdown("### ✂️ 자동 클립 분할")
        st.markdown('<div class="info-box">업로드된 영상을 AI가 장면 단위로 자동 분할합니다.</div>', unsafe_allow_html=True)

        _auto_split_candidates = [c for c in st.session_state.clips if c.get("source") in ("upload", "ytdlp") and os.path.exists(c.get("path", ""))]
        if _auto_split_candidates:
            _split_target = st.selectbox(
                "분할할 영상 선택",
                options=range(len(_auto_split_candidates)),
                format_func=lambda i: f"{_auto_split_candidates[i]['name']} ({_auto_split_candidates[i]['duration']})",
                key="auto_split_target"
            )
            _split_c1, _split_c2 = st.columns(2)
            with _split_c1:
                _split_min = st.slider("최소 클립 길이(초)", 1, 5, 1, key="auto_split_min")
            with _split_c2:
                _split_max = st.slider("최대 클립 길이(초)", 5, 30, 10, key="auto_split_max")

            if st.button("🎬 자동 클립 분할", key="btn_auto_split", type="primary", use_container_width=True):
                _target_clip = _auto_split_candidates[_split_target]
                with st.status("✂️ 장면 분석 + 클립 분할 중...", expanded=True) as _split_status:
                    st.write("📊 장면 전환 지점 분석 중...")
                    _timestamps = clip_analyzer.analyze_scenes(
                        _target_clip["path"],
                        min_dur=float(_split_min),
                        max_dur=float(_split_max)
                    )

                    if _timestamps:
                        st.write(f"🔍 {len(_timestamps)}개 장면 전환 감지 → 분할 중...")
                        _new_clips = clip_analyzer.split_clips(
                            _target_clip["path"],
                            _timestamps,
                            min_dur=float(_split_min)
                        )
                    else:
                        st.write("⚠️ 장면 감지 실패 → 균등 분할 시도 중...")
                        _fallback_ts = clip_analyzer._uniform_split(
                            _target_clip.get("dur_sec", 30),
                            float(_split_min),
                            float(_split_max)
                        )
                        _new_clips = clip_analyzer.split_clips(
                            _target_clip["path"],
                            _fallback_ts,
                            min_dur=float(_split_min)
                        )

                    if _new_clips:
                        st.session_state.clips = [
                            c for c in st.session_state.clips
                            if c.get("path") != _target_clip["path"]
                        ] + _new_clips
                        _split_status.update(label=f"✅ {len(_new_clips)}개 클립 자동 분할 완료!", state="complete")
                        st.success(f"🎉 {len(_new_clips)}개의 클립이 감지되었습니다! → STEP 2로 이동합니다.")
                        st.session_state.current_step = 2
                        st.rerun()
                    else:
                        _split_status.update(label="⚠️ 분할 실패 — 원본 유지", state="error")
                        st.warning("자동 분할에 실패했습니다. 원본 영상이 클립에 유지됩니다.")
        else:
            st.caption("위에서 영상을 먼저 업로드하면 자동 분할 기능을 사용할 수 있습니다.")

    # ╔══════════════════════════════════════════════════════════╗
    # ║ 블록 3: 🔧 참고 도구                                      ║
    # ╚══════════════════════════════════════════════════════════╝
    st.markdown("---")
    st.markdown("## 🔧 블록 3 — 참고 도구")

    # ── ① Pexels 직접 키워드 검색 + AI 추천 ──
    st.markdown("### 🎬 Pexels 배경 영상 검색")
    if not has_key("PEXELS_API_KEY"):
        st.markdown('<div class="demo-banner">⚠️ PEXELS_API_KEY 필요 — Secrets에 등록하세요</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="info-box">직접 키워드를 입력하거나, AI 추천 키워드를 클릭해 검색하세요. (영어 키워드 권장)</div>', unsafe_allow_html=True)

        # AI 추천 키워드
        _ai_pname = st.session_state.get("_w_pname", "") or st.session_state.get("_saved_pname", "") or st.session_state.coupang_product or ""
        if has_key("ANTHROPIC_API_KEY") and _ai_pname:
            if st.button("🤖 AI 추천 키워드 생성", key="ai_pexels_kw_btn", use_container_width=True):
                with st.spinner("AI가 Pexels 검색 키워드를 추천 중..."):
                    _kw_result = call_claude(
                        "Pexels 스톡 영상 검색 전문가. 영어 키워드만 출력.",
                        f"제품: {_ai_pname}\n카테고리: {st.session_state.coupang_category or '기타'}\n\n"
                        "이 제품의 숏폼 영상에 어울리는 Pexels 검색 키워드 5개를 추천해줘.\n"
                        "각 키워드는 영어 2~3단어, 한 줄에 하나씩, 번호 없이 출력.\n"
                        "예시:\nproduct showcase\nminimal background\nlifestyle aesthetic",
                        max_tokens=200
                    )
                    if _kw_result:
                        _keywords = [line.strip() for line in _kw_result.strip().split("\n") if line.strip() and not line.strip().startswith("#")]
                        st.session_state.pexels_ai_keywords = _keywords[:5]
                        st.success(f"✅ {len(st.session_state.pexels_ai_keywords)}개 추천 키워드 생성!")

        # 추천 키워드 버튼 (클릭 시 검색)
        if st.session_state.get("pexels_ai_keywords"):
            st.markdown("**🤖 AI 추천 키워드** (클릭하면 자동 검색):")
            _ai_kw_cols = st.columns(min(len(st.session_state.pexels_ai_keywords), 5))
            _clicked_ai_kw = None
            for ki, _kw_item in enumerate(st.session_state.pexels_ai_keywords):
                with _ai_kw_cols[ki % len(_ai_kw_cols)]:
                    if st.button(f"🔍 {_kw_item}", key=f"ai_kw_{ki}", use_container_width=True):
                        _clicked_ai_kw = _kw_item

            if _clicked_ai_kw:
                with st.spinner(f"'{_clicked_ai_kw}' 검색 중..."):
                    st.session_state.pexels_results = search_pexels(_clicked_ai_kw, 9)
                if st.session_state.pexels_results:
                    st.success(f"✅ '{_clicked_ai_kw}' — {len(st.session_state.pexels_results)}개 영상 발견!")
                else:
                    st.warning("결과 없음. 다른 키워드를 시도해보세요.")

        # 직접 키워드 검색
        st.markdown("---")
        c1, c2, c3 = st.columns([3, 1, 1])
        with c1:
            kw = st.text_input("키워드 직접 입력 (영어 권장)", placeholder="예: product showcase, minimal background", label_visibility="collapsed", key="kw_input")
        with c2:
            n_results = st.selectbox("개수", [6, 9, 12], index=1, label_visibility="collapsed")
        with c3:
            do_search = st.button("🔍 검색", use_container_width=True)

        if do_search and kw:
            with st.spinner(f"'{kw}' 검색 중..."):
                st.session_state.pexels_results = search_pexels(kw, n_results)
            if st.session_state.pexels_results:
                st.success(f"✅ {len(st.session_state.pexels_results)}개 배경 영상 발견!")
            else:
                st.warning("결과 없음. 다른 키워드를 시도해보세요.")

    if st.session_state.pexels_results:
        results = st.session_state.pexels_results
        rows = [results[i:i+3] for i in range(0, len(results), 3)]
        for row in rows:
            cols = st.columns(3)
            for col, v in zip(cols, row):
                with col:
                    if v.get("thumbnail"):
                        try:
                            st.image(v["thumbnail"], use_container_width=True)
                        except:
                            st.markdown('<div style="background:#f7f8fa;height:120px;border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:2rem;">🎬</div>', unsafe_allow_html=True)

                    st.markdown(f"**{v['title'][:30]}**")
                    st.caption(f"⏱ {v['duration']} · 👤 {v['author']}")

                    vid_id = str(v["id"])
                    already = any(c.get("search_id") == vid_id for c in st.session_state.clips)
                    if already:
                        st.markdown("<span class='badge badge-green'>✓ 추가됨</span>", unsafe_allow_html=True)
                    else:
                        px_role = st.selectbox("용도", ["배경", "인트로", "아웃트로"], key=f"role_{vid_id}", label_visibility="collapsed")
                        if st.button(f"＋ {px_role}로 추가", key=f"add_{vid_id}", use_container_width=True):
                            save_dir = _ensure_dir("shortform_clips")
                            dest = save_dir / f"pexels_{vid_id}.mp4"

                            with st.spinner("영상 다운로드 중..."):
                                if v.get("download_url") and download_video(v["download_url"], str(dest)):
                                    dur = get_video_duration(str(dest))
                                    st.session_state.clips.append({
                                        "name": f"[{px_role}] pexels_{vid_id}.mp4",
                                        "path": str(dest),
                                        "duration": f"{int(dur//60)}:{int(dur%60):02d}",
                                        "dur_sec": dur,
                                        "search_id": vid_id,
                                        "source": "pexels",
                                    })
                                    st.rerun()
                                else:
                                    st.error("다운로드 실패")

    st.markdown("---")

    # ── ② YouTube / 인스타그램 참고 링크 ──
    if st.session_state.coupang_product:
        _yt_kw = st.session_state.coupang_product

        # YouTube
        st.markdown("### 📺 YouTube 참고 숏폼")
        if has_key("YOUTUBE_API_KEY"):
            _yt_pname = st.session_state.get("_w_pname", "") or st.session_state.get("_saved_pname", "") or st.session_state.coupang_product or ""
            yt_col1, yt_col2 = st.columns([3, 1])
            with yt_col1:
                yt_keyword = st.text_input("YouTube 검색 키워드", value=_yt_pname, placeholder="예: 에어팟 프로", key="yt_kw_input")
            with yt_col2:
                yt_search_btn = st.button("🔍 유튜브 검색", key="yt_search_btn", use_container_width=True)

            if yt_search_btn and yt_keyword:
                with st.spinner(f"'{yt_keyword}' 유튜브 Shorts 검색 중..."):
                    yt_results = search_youtube_shorts(yt_keyword, n=6)
                    if yt_results:
                        st.session_state.youtube_results = [
                            {"id": yt["id"], "title": yt["title"], "url": yt["url"],
                             "thumbnail": yt.get("thumbnail", ""), "channel": yt.get("channel", ""),
                             "source": "youtube_api"}
                            for yt in yt_results
                        ]
                        st.success(f"✅ {len(yt_results)}개 관련 숏폼 발견!")
                    else:
                        st.warning("검색 결과가 없어요. 다른 키워드를 시도해보세요.")

            if st.session_state.youtube_results:
                yt_results = st.session_state.youtube_results
                yt_rows = [yt_results[i:i+3] for i in range(0, len(yt_results), 3)]
                for yt_row in yt_rows:
                    yt_cols = st.columns(3)
                    for yt_col, yt_v in zip(yt_cols, yt_row):
                        with yt_col:
                            if yt_v.get("thumbnail"):
                                try:
                                    st.image(yt_v["thumbnail"], use_container_width=True)
                                except:
                                    st.markdown('<div style="background:#f7f8fa;height:120px;border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:2rem;">📺</div>', unsafe_allow_html=True)
                            st.markdown(f"**{yt_v['title'][:35]}**")
                            st.caption(f"📺 {yt_v.get('channel', '')}")
                            _yt_c1, _yt_c2 = st.columns(2)
                            with _yt_c1:
                                st.link_button("🔗 링크 열기", yt_v["url"])
                            with _yt_c2:
                                st.text_input("복사용", yt_v["url"], key=f"ytcp_{yt_v['id']}", label_visibility="collapsed")
        else:
            yt_url = f"https://www.youtube.com/results?search_query={_yt_kw}+shorts"
            st.session_state.youtube_results = [
                {"id": "fallback", "title": f"{_yt_kw} shorts 검색", "url": yt_url,
                 "thumbnail": "", "channel": "YouTube", "source": "youtube_fallback"}
            ]
            st.markdown('<div class="info-box">YouTube API 키 없이도 검색 링크를 통해 참고할 수 있어요.</div>', unsafe_allow_html=True)
            _yt_c1, _yt_c2 = st.columns(2)
            with _yt_c1:
                st.link_button("▶ 유튜브에서 검색", yt_url)
            with _yt_c2:
                st.text_input("복사용 링크", yt_url, key="yt_fallback_url", label_visibility="collapsed")

        st.markdown("---")

        # 인스타그램
        st.markdown("### 📸 인스타그램 추천")
        kw = st.session_state.coupang_product.replace(" ", "")
        insta_url = f"https://www.instagram.com/explore/tags/{kw}"
        st.session_state.instagram_links = [insta_url]
        st.markdown(f"📸 **인스타그램 추천**: `#{kw}` 태그")
        _ig_c1, _ig_c2 = st.columns(2)
        with _ig_c1:
            st.link_button("🔗 링크 열기", insta_url)
        with _ig_c2:
            st.text_input("복사용 링크", insta_url, key="insta_copy_url", label_visibility="collapsed")
        st.caption("인스타에서 이 키워드로 검색해 트렌드를 확인하세요.")
        st.markdown("---")

    # ── ③ 타오바오 + AI 트렌드 키워드 ──
    with st.expander("📥 타오바오 영상 다운로드 방법", expanded=False):
        _tb_query = st.session_state.get("coupang_product", "") or st.session_state.get("_w_pname", "") or st.session_state.get("_saved_pname", "")
        st.markdown("**Step 1.** 타오바오에서 제품명으로 검색")
        _tb_url = f"https://s.taobao.com/search?q={_tb_query}" if _tb_query else "https://www.taobao.com"
        st.link_button("🔗 타오바오에서 검색하기 ▶", _tb_url)
        st.markdown("**Step 2.** 상세페이지에서 제조사 홍보 영상 확인")
        st.markdown("**Step 3.** 크롬 확장프로그램으로 영상 저장")
        st.link_button("🔗 Video Downloader Pro 설치하기 ▶", "https://chrome.google.com/webstore/detail/video-downloader-pro/elicpjhcidhpjomhibiffojpinpmmpil")
        st.markdown("**Step 4.** 다운받은 영상을 **블록 2 → 영상 직접 업로드**에서 올리세요")

    # AI 트렌드 키워드 추천
    st.markdown("### 🤖 AI 트렌드 키워드 추천")
    st.markdown('<div class="info-box">AI가 제품과 관련된 트렌드 숏폼 키워드와 영상 포맷을 추천합니다.</div>', unsafe_allow_html=True)

    if not has_key("ANTHROPIC_API_KEY"):
        st.markdown('<div class="demo-banner">⚠️ ANTHROPIC_API_KEY 필요</div>', unsafe_allow_html=True)
    else:
        _ai_pname2 = st.session_state.get("_w_pname", "") or st.session_state.get("_saved_pname", "") or st.session_state.coupang_product or ""
        _ai_cat2 = st.session_state.coupang_category or "기타"

        if st.button("✨ AI 키워드 추천 받기", key="ai_trend_btn", use_container_width=True, disabled=(not _ai_pname2)):
            with st.spinner("AI가 트렌드 키워드를 분석 중..."):
                trend_result = call_claude(
                    "숏폼 트렌드 전문가. 핵심만 간결하게 출력.",
                    f"제품: {_ai_pname2}\n카테고리: {_ai_cat2}\n\n"
                    "다음 3가지를 알려줘:\n"
                    "1. 이 제품 관련 인기 숏폼 트렌드 키워드 5개 (영어 + 한국어)\n"
                    "2. 추천 영상 포맷 3가지 (예: 언박싱, ASMR, 비포애프터 등)\n"
                    "3. Pexels/YouTube 검색에 좋은 영어 키워드 3개\n\n"
                    "각 항목을 번호로 구분해서 출력해줘."
                )
                if trend_result:
                    st.session_state["_ai_trend_result"] = trend_result
                    st.success("✅ AI 추천 완료!")

        if st.session_state.get("_ai_trend_result"):
            st.markdown(st.session_state["_ai_trend_result"])

        if not _ai_pname2:
            st.caption("💡 위에서 제품명을 입력하면 AI 추천을 받을 수 있어요.")

    _render_nav_buttons()


# ═════════════════════════════════════════════════════════════════
# render_step2: 🎬 클립 편집
# ═════════════════════════════════════════════════════════════════
def render_step2():
    target_dur = st.session_state.get("_w_target_dur", 30)

    st.markdown('<div class="ux-card"><div class="ux-card-title">STEP 02</div><h4>클립 편집</h4><p class="ux-sub">클립 순서를 정리하고 용도를 태그하세요. 인트로 &rarr; 제품소개 &rarr; 사용장면 &rarr; 아웃트로 순서 추천!</p></div>', unsafe_allow_html=True)

    if st.session_state.clips:
        clips = st.session_state.clips
        to_remove = []
        for i, clip in enumerate(clips):
            c1, c2, c3, c4, c_tag, c5, c6 = st.columns([0.6, 0.4, 0.4, 3, 1.5, 1.0, 0.7])
            with c1:
                src_badge = "badge-blue" if clip.get("source") == "pexels" else ("badge-green" if clip.get("source") == "kenburns" else "badge-dark")
                st.markdown(f"<span class='badge {src_badge}'>#{i+1:02d}</span>", unsafe_allow_html=True)
            with c2:
                if i > 0 and st.button("↑", key=f"up_{i}"):
                    clips[i-1], clips[i] = clips[i], clips[i-1]
                    st.session_state.clips = clips
                    st.rerun()
            with c3:
                if i < len(clips)-1 and st.button("↓", key=f"dn_{i}"):
                    clips[i+1], clips[i] = clips[i], clips[i+1]
                    st.session_state.clips = clips
                    st.rerun()
            with c4:
                nm = clip["name"][:40] + "..." if len(clip["name"]) > 40 else clip["name"]
                st.markdown(f"<div style='padding-top:6px;'>{nm}</div>", unsafe_allow_html=True)
            with c_tag:
                # 기존 값 보존 — 없을 때만 초기화
                if "usage_tag" not in clip:
                    clip["usage_tag"] = "제품소개"
                tag_opts = ["인트로", "제품소개", "사용장면", "아웃트로"]
                cur_tag = clip["usage_tag"]
                clips[i]["usage_tag"] = st.selectbox("용도", tag_opts,
                    index=tag_opts.index(cur_tag) if cur_tag in tag_opts else 1,
                    key=f"utag_{i}", label_visibility="collapsed")
            with c5:
                st.caption(f"⏱ {clip['duration']}")
            with c6:
                if st.button("🗑️", key=f"del_{i}"):
                    to_remove.append(i)
        for idx in sorted(to_remove, reverse=True):
            st.session_state.clips.pop(idx)
        if to_remove:
            st.rerun()

        ca, cb, cc = st.columns(3)
        with ca:
            st.metric("📼 클립 수", f"{len(clips)}개")
        with cb:
            t = sum(c.get("dur_sec", 0) for c in clips)
            st.metric("⏱ 총 길이", f"{int(t//60)}분 {int(t%60)}초")
        with cc:
            st.metric("🎯 목표", f"{target_dur}초")

        # ── AI 순서 자동 추천 ──
        order_c1, order_c2 = st.columns([1, 1])
        with order_c1:
            if st.button("🤖 AI 순서 추천", key="auto_order_btn", use_container_width=True,
                         help="인트로 → 제품소개 → 사용장면 → 아웃트로 순으로 자동 정렬"):
                reordered = auto_order_clips(clips)
                st.session_state.clips = reordered
                st.success("✅ AI가 최적 순서로 정렬했습니다! (인트로 → 제품소개 → 사용장면 → 아웃트로)")
                st.rerun()
        with order_c2:
            if st.button("🔀 순서 랜덤 섞기", key="random_order_btn", use_container_width=True):
                import random as _rnd
                _rnd.shuffle(st.session_state.clips)
                st.rerun()

        if st.button("✅ 순서 확정"):
            st.session_state.clip_order = [c["path"] for c in clips]
            st.success(f"✅ {len(clips)}개 확정!")
    else:
        st.markdown('<div style="text-align:center;padding:40px 0;color:#8b95a1;">📂 STEP 1에서 영상을 검색/생성하거나 업로드하세요</div>', unsafe_allow_html=True)
        _c_back = st.columns([1, 2, 1])[1]
        with _c_back:
            if st.button("← STEP 1 소스 선택으로 이동", key="back_to_step1_from2", use_container_width=True):
                st.session_state.current_step = 1
                st.rerun()

    _render_nav_buttons()


# ═════════════════════════════════════════════════════════════════
# render_step3: 🎙️ 자막 + 음성
# ═════════════════════════════════════════════════════════════════
def render_step3():
    target_dur = st.session_state.get("_w_target_dur", 30)
    crop_ratio = st.session_state.get("_w_crop_ratio", "9:16 세로형 (숏폼)")

    st.markdown('<div class="ux-card"><div class="ux-card-title">STEP 03</div><h4>영상 생성</h4><p class="ux-sub">AI가 제목 · 대본 · 음성 · 자막을 자동 생성합니다.</p></div>', unsafe_allow_html=True)

    if not has_key("ANTHROPIC_API_KEY"):
        st.markdown('<div class="demo-banner">⚠️ ANTHROPIC_API_KEY 미설정 — AI 기능이 작동하지 않습니다</div>', unsafe_allow_html=True)

    # ═══════ ⚡ 3 프리셋 ═══════
    # 1-A: 8개 개별 토글 → 3 프리셋으로 단순화. 고급 사용자는 expander로 개별 제어.
    st.markdown('<div class="ux-card"><div class="ux-card-title">MODE</div><h4>⚡ 영상 모드 선택</h4><p class="ux-sub">한 번에 전부 설정. 3초 안에 고르세요.</p></div>', unsafe_allow_html=True)

    PRESETS = {
        "fast": {
            "label": "🚀 빠른 모드",
            "desc": "1개 영상 · 최소 옵션 · 1분 내 조립",
            "hook_test": False,
            "hook_count": 2,
            "pattern_interrupt": False,
            "retention_booster": True,
            "anti_shadowban": False,
        },
        "standard": {
            "label": "✨ 표준 모드 (권장)",
            "desc": "1개 영상 · 품질 최적화 토글 전체 ON",
            "hook_test": False,
            "hook_count": 2,
            "pattern_interrupt": True,
            "retention_booster": True,
            "anti_shadowban": True,
        },
        "ab_test": {
            "label": "🧪 A·B 테스트 모드",
            "desc": "첫 3초 다른 영상 2~3개 · 어떤 Hook이 먹히는지 테스트",
            "hook_test": True,
            "hook_count": 2,
            "pattern_interrupt": True,
            "retention_booster": True,
            "anti_shadowban": True,
        },
    }

    _current_preset = st.session_state.get("active_preset", "standard")
    _preset_cols = st.columns(3)
    _preset_keys = list(PRESETS.keys())
    for _i, _pk in enumerate(_preset_keys):
        with _preset_cols[_i]:
            _cfg = PRESETS[_pk]
            _is_active = _current_preset == _pk
            _btn_type = "primary" if _is_active else "secondary"
            _active_mark = "  ✅" if _is_active else ""
            st.markdown(f"**{_cfg['label']}**{_active_mark}")
            st.caption(_cfg['desc'])
            if st.button(f"선택", key=f"preset_btn_{_pk}", type=_btn_type, use_container_width=True):
                st.session_state.active_preset = _pk
                st.session_state.hook_test_enabled = _cfg["hook_test"]
                st.session_state.hook_version_count = _cfg["hook_count"]
                st.session_state.pattern_interrupt_enabled = _cfg["pattern_interrupt"]
                st.session_state.retention_booster_enabled = _cfg["retention_booster"]
                st.session_state.anti_shadowban_enabled = _cfg["anti_shadowban"]
                st.rerun()

    # 현재 활성 옵션 요약
    _active_tags = []
    if st.session_state.hook_test_enabled: _active_tags.append(f"🎯 Hook A/B ({st.session_state.hook_version_count}버전)")
    if st.session_state.pattern_interrupt_enabled: _active_tags.append("⚡ Pattern Interrupt")
    if st.session_state.retention_booster_enabled: _active_tags.append("📈 Retention Booster")
    if st.session_state.anti_shadowban_enabled: _active_tags.append("🛡️ Anti-Shadowban")
    if _active_tags:
        st.markdown(f'<div class="info-box">활성 옵션: {" · ".join(_active_tags)}</div>', unsafe_allow_html=True)

    # ── 고급 설정 (접기) ──
    with st.expander("⚙️ 고급 설정 — 개별 토글 (프리셋 덮어쓰기)"):
        _adv_c1, _adv_c2 = st.columns(2)
        with _adv_c1:
            st.session_state.hook_test_enabled = st.checkbox(
                "🎯 Hook A/B 테스트 (첫 3초만 다른 영상 여러 개)",
                value=st.session_state.hook_test_enabled,
                key="opt_hook_test",
            )
            if st.session_state.hook_test_enabled:
                st.session_state.hook_version_count = st.radio(
                    "버전 수", [2, 3], horizontal=True, key="opt_hook_count",
                    index=0 if st.session_state.hook_version_count == 2 else 1
                )
            st.session_state.pattern_interrupt_enabled = st.checkbox(
                "⚡ Pattern Interrupt (중간 zoom/cut/강조 자동 삽입)",
                value=st.session_state.pattern_interrupt_enabled,
                key="opt_pattern_interrupt",
            )
        with _adv_c2:
            st.session_state.retention_booster_enabled = st.checkbox(
                "📈 Retention Booster (완시율 최적화)",
                value=st.session_state.retention_booster_enabled,
                key="opt_retention_booster",
            )
            st.session_state.anti_shadowban_enabled = st.checkbox(
                "🛡️ Anti-Shadowban (해시값 미세 변형, 중복감지 우회)",
                value=st.session_state.anti_shadowban_enabled,
                key="opt_anti_shadowban",
            )
        st.caption("※ 개별 토글 변경 시 프리셋 ✅는 유지되지만 실제 설정은 토글 값이 우선합니다.")
    st.markdown("---")

    # ── AI 제목 9개 생성 (쿠팡 전용) ──
    if st.session_state.coupang_product:
        pname = st.session_state.coupang_product
        pcat = st.session_state.coupang_category

        st.markdown("#### 1️⃣ AI 제목 자동 생성 (9개)")
        st.markdown('<div class="info-box">3가지 유형 × 3개씩 = 총 9개 제목을 AI가 생성합니다. 📌 버튼으로 원하는 제목을 바로 적용하세요.</div>', unsafe_allow_html=True)

        if st.button("✨ AI 제목 9개 생성", key="gen_titles", disabled=not has_key("ANTHROPIC_API_KEY")):
            with st.spinner("3가지 유형 × 3개 제목 생성 중..."):
                cmode = st.session_state.content_mode
                mode_emphasis = {
                    "클릭유도형": "궁금증 유발형을 특히 강렬하게 만들어줘.",
                    "구매전환형": "혜택강조형을 특히 매력적으로 만들어줘.",
                    "리뷰형": "문제해결형을 실제 사용 경험 중심으로 만들어줘.",
                    "비교형": "궁금증 유발형에 비교 요소를 넣어줘.",
                    "문제해결형": "문제해결형을 가장 공감가게 만들어줘.",
                    "바이럴형": "궁금증 유발형을 밈/유머 스타일로 만들어줘.",
                }
                result = call_claude(
                    "숏폼 제목 전문가. 정확히 아래 형식으로 출력. 제목만 출력.",
                    f"제품: {pname}\n카테고리: {pcat}\n콘텐츠 목적: {cmode}\n{mode_emphasis.get(cmode, '')}\n\n아래 3가지 유형별로 각 3개씩 총 9개의 숏폼 제목을 만들어줘.\n\n[궁금증유발]\n- '이거 모르면 손해', '진짜 이게 돼?' 같은 호기심 자극 스타일\n[문제해결]\n- '이것 때문에 고민 끝', '해결한 제품' 같은 솔루션 제시 스타일\n[혜택강조]\n- '이 가격에?', '가성비 끝판왕' 같은 가격/혜택 강조 스타일\n\n조건:\n- 각 제목 15자 이내\n- 이모지 1개 포함\n- 유형 라벨 없이, 3줄 빈 줄로 유형 구분\n- 총 9줄 출력 (유형당 3줄)\n- 매번 완전히 새로운 표현과 구조 사용\n- 숫자형, 질문형, 감탄형, 비유형, 명령형 등 다양한 스타일 골고루 혼합"
                )
                if result:
                    lines = [l.strip() for l in result.strip().split("\n") if l.strip()]
                    titles = []
                    type_names = ["궁금증유발", "문제해결", "혜택강조"]
                    type_idx = 0
                    count = 0
                    for l in lines:
                        clean = l.lstrip("0123456789.-) ·•")
                        if clean.startswith("[") or clean.startswith("【"):
                            continue
                        if clean:
                            ttype = type_names[min(type_idx, 2)]
                            titles.append({"text": clean, "type": ttype})
                            count += 1
                            if count % 3 == 0:
                                type_idx += 1
                    st.session_state.generated_titles = titles[:9]
                else:
                    st.markdown('<div class="demo-banner">⚠️ API 키 없음 — 데모 모드에서는 생성되지 않습니다</div>', unsafe_allow_html=True)

        if st.session_state.generated_titles:
            type_badges = {"궁금증유발": "badge-red", "문제해결": "badge-blue", "혜택강조": "badge-green"}
            current_type = ""
            for ti, title_item in enumerate(st.session_state.generated_titles):
                ttype = title_item.get("type", "")
                if ttype != current_type:
                    current_type = ttype
                    badge_cls = type_badges.get(ttype, "badge-gray")
                    st.markdown(f'<span class="badge {badge_cls}" style="margin-top:8px;">{ttype}</span>', unsafe_allow_html=True)
                tc1, tc2 = st.columns([5, 1])
                with tc1:
                    st.markdown(f"&nbsp;&nbsp;`{title_item['text']}`")
                with tc2:
                    if st.button("📌 적용", key=f"title_{ti}", use_container_width=True):
                        st.session_state.selected_title = title_item["text"]
                        st.session_state.coupang_titles = title_item["text"]
                        st.success(f"✅ 제목 적용됨!")
                        st.rerun()

            if st.session_state.selected_title:
                st.markdown(f'<div class="info-box">현재 적용된 제목: <strong>{st.session_state.selected_title}</strong></div>', unsafe_allow_html=True)

        st.markdown("---")

        # ── 쿠팡 스크립트 자동 생성 ──
        st.markdown("#### 📋 쿠팡 숏폼 스크립트 자동 생성")

        # ── 톤 / 강조 포인트 / 길이 선택 UI ──
        _sc_c1, _sc_c2, _sc_c3 = st.columns(3)
        with _sc_c1:
            _script_tone = st.selectbox("말투", ["친근한 반말", "정중한 존댓말", "전문가 톤"], key="_w_script_tone")
        with _sc_c2:
            _script_emphasis = st.selectbox("강조 포인트", ["가격", "품질", "편의성", "희소성"], key="_w_script_emphasis")
        with _sc_c3:
            _script_length = st.selectbox("길이", ["15초 (초단편)", "30초 (표준)", "60초 (롱폼)"], key="_w_script_length")

        _len_map = {"15초 (초단편)": ("15초", "15~20초", "3~5문장"), "30초 (표준)": ("30초", "30~45초", "8~12문장"), "60초 (롱폼)": ("60초", "50~60초", "15~20문장")}
        _len_label, _len_range, _len_sentences = _len_map.get(_script_length, ("30초", "30~45초", "8~12문장"))

        # ── 🌟 개인 사연 / 추가 컨텍스트 (대본 품질 폭발 핵심) ──
        st.session_state["_personal_context"] = st.text_area(
            "🌟 개인 사연·배경 (선택, 입력하면 대본 품질 ↑↑)",
            value=st.session_state.get("_personal_context", ""),
            placeholder="예: 화장품 알러지로 1년간 응급실 갔던 사람인데 이거 쓰고 처음 잠들었어 / "
                        "자취 3년차인데 라면 박스로 사면 한 봉 700원 / 강아지 입맛 까다로운데 이건 흡입함",
            height=70,
            help="구체적 개인 사연을 1줄 입력하면 LLM이 그걸 살려서 대본 품질이 크게 올라갑니다. "
                 "수치/시점/대상이 구체적일수록 좋아요.",
            key="_personal_context_input",
        )

        if st.button("✨ AI 스크립트 생성", key="gen_coupang_script", disabled=not has_key("ANTHROPIC_API_KEY")):
            with st.spinner("스크립트 생성 중..."):
                cmode = st.session_state.content_mode
                mode_guide = {
                    "클릭유도형": "궁금증과 충격적 표현으로 클릭 유도. 첫 문장에 '이걸 모르면...' 같은 호기심 자극.",
                    "구매전환형": "할인·한정·혜택 강조. CTA에서 즉시 구매 촉진. '지금 안 사면 후회' 느낌.",
                    "리뷰형": "실제 사용 경험 중심. 장점·단점 솔직하게. 신뢰감 있는 톤.",
                    "비교형": "경쟁 제품 대비 차별점 강조. 'A vs B' 구조. 데이터·수치 활용.",
                    "문제해결형": "일상 불편함 제시 → 이 제품이 해결. before/after 느낌.",
                    "바이럴형": "밈·유머·감성 자극. 공유하고 싶은 콘텐츠. 트렌디한 표현.",
                }
                _tpl_tone = ""
                _active_tpl = TEMPLATES.get(st.session_state.get("active_template", ""), {})
                if _active_tpl.get("script_tone"):
                    _tpl_tone = f"\n템플릿 톤: {_active_tpl['script_tone']}"

                _tone_guide = {"친근한 반말": "친구한테 말하듯 반말로. '야 이거 진짜 대박이야' 느낌. 이모지 자유롭게 사용.",
                               "정중한 존댓말": "정중하지만 딱딱하지 않게. '이 제품 정말 추천드려요' 느낌. 존댓말 사용.",
                               "전문가 톤": "전문 리뷰어처럼 객관적이고 신뢰감 있게. 데이터와 수치 활용."}
                _emph_guide = {"가격": "가격 대비 성능, 할인율, '이 가격에 이 퀄리티?' 강조. 숫자를 적극 활용.",
                               "품질": "소재, 내구성, 디테일, 마감 품질 강조. 실제 사용감 묘사.",
                               "편의성": "사용 편리함, 시간 절약, 간편함 강조. before/after 비교.",
                               "희소성": "한정 수량, 품절 임박, '지금 아니면 못 삼' 분위기 조성. 긴급성 강조."}

                # 우선순위: 사용자 선택 카테고리 (UI 한국어 → 내부 ID 매핑) → URL 추론
                _ui_cat = pcat or st.session_state.get("coupang_category", "")
                _mapped_cat = category_templates.map_ui_category(_ui_cat) if _ui_cat else ""
                _inferred_cat = _mapped_cat if _mapped_cat != "general" else \
                                 category_templates.infer_category(pname, pcat)
                _active_uc = st.session_state.get("active_use_case", "coupang_affiliate")
                _personal_ctx = st.session_state.get("_personal_context", "")
                st.session_state["_last_inferred_category"] = _inferred_cat

                # 카테고리에 맞는 3가지 viral 패턴 자동 선정
                _three_patterns = viral_patterns.pick_three_patterns(_inferred_cat, _active_uc)

                # 3개 변형 동시 생성 (각각 다른 viral 패턴)
                _variants = []
                for _pid in _three_patterns:
                    _sys, _usr = script_prompts.build_master_prompt(
                        use_case=_active_uc, category=_inferred_cat, product=pname,
                        tone=_script_tone, target_chars=200,
                        personal_context=_personal_ctx, pattern_id=_pid,
                    )
                    _script_v = call_claude(_sys, _usr, prompt_type=f"script_viral_{_pid}") or ""
                    if _script_v:
                        _judge_v = script_judge.judge_script(
                            _script_v, product=pname, category=_inferred_cat,
                            use_case=_active_uc, min_score=85,
                        )
                        _variants.append({
                            "pattern_id": _pid,
                            "pattern_label": viral_patterns.get_pattern(_pid)["label"],
                            "script": _script_v,
                            "judge": _judge_v,
                            "score": _judge_v.get("total", 0),
                        })

                if _variants:
                    # 점수 높은 순으로 정렬
                    _variants.sort(key=lambda v: -v["score"])
                    st.session_state["_script_variants"] = _variants
                    # 자동으로 가장 높은 점수 선택
                    st.session_state.coupang_script = _variants[0]["script"]
                    st.session_state["_last_judge"] = _variants[0]["judge"]
                    st.session_state["_last_attempts"] = len(_variants)
                    st.session_state["_selected_variant_idx"] = 0
                else:
                    st.markdown('<div class="demo-banner">⚠️ API 키 없음 — 데모 모드에서는 생성되지 않습니다</div>', unsafe_allow_html=True)

        # ── 3가지 viral 패턴 변형 비교 + 선택 ──
        _variants = st.session_state.get("_script_variants", [])
        if _variants and len(_variants) > 1:
            st.markdown("### 🎨 3가지 viral 패턴 — 마음에 드는 거 선택")
            _v_cols = st.columns(len(_variants))
            _curr_idx = st.session_state.get("_selected_variant_idx", 0)
            for _vi, _v in enumerate(_variants):
                with _v_cols[_vi]:
                    _is_sel = (_vi == _curr_idx)
                    _emoji = "🟢" if _v["score"] >= 85 else ("🟡" if _v["score"] >= 70 else "🔴")
                    _border = "3px solid #FF6B35" if _is_sel else "1px solid #E5E7EB"
                    st.markdown(
                        f'<div style="border:{_border};border-radius:12px;padding:12px;'
                        f'background:#fff;height:100%;">'
                        f'<div style="font-size:.8rem;color:#FF6B35;font-weight:700;">{_v["pattern_label"]}</div>'
                        f'<div style="font-size:1.4rem;font-weight:800;margin:6px 0;">'
                        f'{_emoji} {_v["score"]}<span style="font-size:.8rem;color:#888;">/100</span></div>'
                        f'</div>', unsafe_allow_html=True)
                    st.text_area(
                        f"v{_vi+1}", value=_v["script"], height=200,
                        key=f"_variant_show_{_vi}", label_visibility="collapsed"
                    )
                    if st.button(
                        "✅ 이걸로 선택" if not _is_sel else "👉 현재 선택됨",
                        key=f"_pick_variant_{_vi}",
                        type="primary" if _is_sel else "secondary",
                        use_container_width=True,
                        disabled=_is_sel,
                    ):
                        st.session_state["_selected_variant_idx"] = _vi
                        st.session_state.coupang_script = _v["script"]
                        st.session_state["_last_judge"] = _v["judge"]
                        st.rerun()
            st.markdown("---")

        # ── 점수 + 차원별 표시 + 다시 생성 버튼 ──
        _judge = st.session_state.get("_last_judge", {})
        if _judge:
            _score = _judge.get("total", 0)
            _badge = "🟢" if _score >= 85 else ("🟡" if _score >= 70 else "🔴")
            _atts = st.session_state.get("_last_attempts", 1)
            _sc1, _sc2 = st.columns([3, 1])
            with _sc1:
                st.markdown(f"### {_badge} 품질 점수 **{_score}/100** ({_atts}회 시도)")
                if _judge.get("improvement"):
                    st.info(f"💡 **개선 여지**: {_judge['improvement']}")
            with _sc2:
                if st.button("🔁 다시 생성", key="regen_script", type="primary",
                              use_container_width=True):
                    # 강제로 다시 생성 (직전 점수를 hint로 활용)
                    st.session_state.pop("coupang_script", None)
                    st.session_state.pop("_last_judge", None)
                    st.rerun()
            # 차원별 점수 펼치기
            if _judge.get("scores"):
                with st.expander("📊 차원별 평가 펼치기"):
                    for k, v in _judge["scores"].items():
                        if not v.get("score"):
                            continue
                        _label = {
                            "hook_impact": "1️⃣ Hook 손가락 멈춤도",
                            "category_fit": "2️⃣ 카테고리 적합성",
                            "specificity": "3️⃣ 구체성 (수치/사례)",
                            "anti_cliche": "4️⃣ ChatGPT 클리셰 회피",
                            "conversion_power": "5️⃣ 구매 욕구 자극",
                            "length_fit": "📏 길이 적합성",
                            "cta_clarity": "🎯 CTA 명확성",
                        }.get(k, k)
                        _s = v.get("score", 0)
                        _emoji = "🟢" if _s >= 16 else ("🟡" if _s >= 11 else "🔴")
                        st.markdown(f"{_emoji} **{_label}**: {_s}/20 — {v.get('reason', '')[:120]}")

        if st.session_state.coupang_script:
            st.session_state.coupang_script = st.text_area(
                "스크립트 (수정 가능)", value=st.session_state.coupang_script, height=180
            )
            if st.button("📋 이 스크립트를 메인 스크립트에 적용", key="apply_script"):
                st.session_state.script = st.session_state.coupang_script
                st.success("✅ 메인 스크립트에 적용됨!")

        st.markdown("---")

    # ── 후킹 문구 + 메인 스크립트 ──
    pn = st.session_state.get("_w_pname", "") or st.session_state.get("_saved_pname", "") or st.session_state.coupang_product
    if not pn:
        st.warning("⚠️ STEP 1에서 제품명을 입력하거나, 쿠팡 URL을 먼저 추출하세요.")
    else:
        t1, t2 = st.columns(2)
        with t1:
            tone = st.selectbox("톤", ["🔥 강렬하게", "😊 친근하게", "💎 고급스럽게", "📢 구매유도형"])
        with t2:
            lang = st.selectbox("언어", ["한국어", "영어", "한국어+영어 혼용"])

        # ── 첫 3초 후킹 문구 ──
        st.markdown("---")
        st.markdown('<div class="card"><div class="card-label">HOOK</div><h3>🪝 첫 3초 후킹 문구</h3></div>', unsafe_allow_html=True)
        st.markdown('<div class="info-box">시청자를 멈추게 하는 첫 3초! AI가 콘텐츠 목적에 맞는 후킹 문구 5개를 제안합니다.</div>', unsafe_allow_html=True)

        cmode = st.session_state.content_mode
        _pdesc = st.session_state.get("_w_pdesc", "") or ""
        if st.button("🪝 후킹 문구 5개 생성", key="gen_hooks", disabled=not has_key("ANTHROPIC_API_KEY")):
            with st.spinner("후킹 문구 생성 중..."):
                hook_result = call_claude(
                    "숏폼 후킹 전문가. 번호 매기지 말고 한 줄씩만 출력. 각 줄이 하나의 후킹 문구.",
                    f"제품: {pn}\n설명: {_pdesc or '없음'}\n카테고리: {st.session_state.coupang_category or '일반'}\n콘텐츠 목적: {cmode}\n\n이 제품의 숏폼 영상 '첫 3초 후킹 문구' 5개를 만들어줘.\n\n조건:\n- '{cmode}' 스타일에 맞게 작성\n- 시청자가 스크롤을 멈추고 보게 만드는 한 줄\n- 15자 이내, 짧고 강렬하게\n- 이모지 1개 포함 가능\n- 궁금증/충격/공감/유머 활용\n- 숫자 매기지 말고 문구만 출력"
                )
                if hook_result:
                    hooks = [h.strip().lstrip("0123456789.-) ") for h in hook_result.strip().split("\n") if h.strip()]
                    st.session_state.hook_suggestions = hooks[:5]
                else:
                    st.markdown('<div class="demo-banner">⚠️ API 키 없음 — 후킹 문구 생성 불가</div>', unsafe_allow_html=True)

        if st.session_state.hook_suggestions:
            st.markdown(f"**`{cmode}` 스타일 후킹 문구:**")
            for hi, hook in enumerate(st.session_state.hook_suggestions):
                hc1, hc2 = st.columns([5, 1])
                with hc1:
                    st.markdown(f"&nbsp;&nbsp;`{hook}`")
                with hc2:
                    if st.button("📌 적용", key=f"hook_{hi}", use_container_width=True):
                        st.session_state.selected_hook = hook
                        if st.session_state.script:
                            st.session_state.script = hook + "\n\n" + st.session_state.script
                        else:
                            st.session_state.script = hook + "\n\n"
                        st.success(f"✅ 후킹 문구 적용됨: '{hook}'")
                        st.rerun()

            if st.session_state.selected_hook:
                st.markdown(f'<div class="info-box">현재 적용된 훅: <strong>{st.session_state.selected_hook}</strong></div>', unsafe_allow_html=True)

        st.markdown("---")

        # ── AI 스크립트 생성 ──
        if st.button("🤖 AI 스크립트 생성"):
            with st.spinner("생성 중..."):
                cmode = st.session_state.content_mode
                mode_guide = {
                    "클릭유도형": "궁금증과 충격적 표현으로 클릭 유도",
                    "구매전환형": "할인·한정·혜택 강조, 즉시 구매 촉진",
                    "리뷰형": "실제 사용 경험 중심, 장점·단점 솔직하게",
                    "비교형": "경쟁 제품 대비 차별점 강조, 데이터 활용",
                    "문제해결형": "일상 불편함 → 이 제품이 해결, before/after",
                    "바이럴형": "밈·유머·감성 자극, 공유하고 싶은 콘텐츠",
                }
                hook_instruction = ""
                if st.session_state.selected_hook:
                    hook_instruction = f"\n첫 문장은 반드시 이것으로 시작해: '{st.session_state.selected_hook}'"
                result = call_claude(
                    "숏폼 광고 카피라이터. 스크립트만 출력.",
                    f"제품:{pn}\n설명:{_pdesc or '없음'}\n톤:{tone}\n언어:{lang}\n길이:{target_dur}초\n콘텐츠 목적:{cmode}\n스타일 가이드:{mode_guide.get(cmode, '')}\n조건:'{cmode}' 목적에 맞게, 첫 문장 강렬, 구매유도, 짧은 문장{hook_instruction}"
                )
                if result:
                    st.session_state.script = result
                    st.session_state.script_history.append({"v": len(st.session_state.script_history)+1, "text": result, "note": "최초 생성"})
                else:
                    st.markdown('<div class="demo-banner">⚠️ API 키 없음 — 스크립트 생성 불가</div>', unsafe_allow_html=True)

        if st.session_state.script:
            st.session_state.script = st.text_area("📝 스크립트 (직접 수정 가능)", value=st.session_state.script, height=120)

            req_col1, req_col2 = st.columns([4, 1])
            with req_col1:
                s_req = st.text_input("AI 수정 요청", placeholder="예: 더 짧게 / 더 재미있게 / 마지막에 가격 추가", label_visibility="collapsed", key="s_req")
            with req_col2:
                apply_s = st.button("✨ 반영", key="apply_s", use_container_width=True)

            if apply_s and s_req:
                with st.spinner("수정 중..."):
                    result = call_claude(
                        "스크립트 편집 전문가. 수정된 스크립트만 출력.",
                        f"현재 스크립트:\n{st.session_state.script}\n\n수정 요청: {s_req}"
                    )
                    if result:
                        st.session_state.script = result
                        st.session_state.script_history.append({"v": len(st.session_state.script_history)+1, "text": result, "note": s_req})
                        st.rerun()

    # ── TTS 설정 & 생성 ──
    st.markdown("---")
    st.markdown('<div class="card"><div class="card-label">TTS</div><h3>🎙️ TTS 음성 생성</h3></div>', unsafe_allow_html=True)

    # ── 🔊 음성 생성 엔진 선택 ──
    _has_clova = has_key("CLOVA_TTS_CLIENT_ID")
    _has_el = has_key("ELEVENLABS_API_KEY")
    _engine_opts = [
        "🆓 Edge TTS (무료, API 키 불필요)",
        "🌍 ElevenLabs (자연스럽고 감정 풍부)",
        "🇰🇷 네이버 클로바 (안정적, 한국어 특화)",
    ]
    _engine_map = {
        _engine_opts[0]: "edge",
        _engine_opts[1]: "elevenlabs",
        _engine_opts[2]: "clova",
    }
    _engine_reverse = {"edge": _engine_opts[0], "elevenlabs": _engine_opts[1], "clova": _engine_opts[2]}
    _default_engine = st.session_state.get("tts_engine", "edge")
    if _default_engine not in ("edge", "elevenlabs", "clova"):
        _default_engine = "edge"
    _cur_label = _engine_reverse.get(_default_engine, _engine_opts[0])
    _sel_engine = st.radio("🔊 음성 생성 엔진 선택", _engine_opts, horizontal=True,
                           index=_engine_opts.index(_cur_label) if _cur_label in _engine_opts else 0,
                           key="_w_tts_engine")
    st.session_state.tts_engine = _engine_map[_sel_engine]

    with st.expander("🎙️ TTS 설정", expanded=False):
        if st.session_state.tts_engine == "clova":
            tts_voice = st.selectbox("클로바 음성", [
                "nara - 여성 (자연스러움)", "jinho - 남성 (신뢰감)",
                "nbora - 밝은 여성", "ndain - 차분한 남성",
            ])
            elevenlabs_voice_id = None
        elif st.session_state.tts_engine == "edge":
            edge_voices = {
                "SunHi - 여성 (자연스러움)": "ko-KR-SunHiNeural",
                "InJoon - 남성 (신뢰감)": "ko-KR-InJoonNeural",
                "Hyunsu - 다국어 남성": "ko-KR-HyunsuMultilingualNeural",
            }
            tts_voice = st.selectbox("Edge 음성", list(edge_voices.keys()))
            st.session_state["_edge_voice"] = edge_voices[tts_voice]
            elevenlabs_voice_id = None
        else:
            el_voices = {
                "Rachel (여성, 차분)": "21m00Tcm4TlvDq8ikWAM",
                "Bella (여성, 밝음)": "EXAVITQu4vr4xnSDxMaL",
                "Antoni (남성, 신뢰감)": "ErXwobaYiN019PkySvjV",
                "Josh (남성, 젊음)": "TxGEqnHWrfWFTfGW9XjX",
            }
            tts_voice = st.selectbox("ElevenLabs 음성", list(el_voices.keys()))
            elevenlabs_voice_id = el_voices[tts_voice]
        tts_speed = st.slider("속도", 0.7, 1.5, 1.0, 0.1)

    if st.session_state.script:
        if st.session_state.tts_engine == "edge":
            has_tts_key = True  # 키 불필요
        elif st.session_state.tts_engine == "clova":
            has_tts_key = _has_clova
        else:
            has_tts_key = _has_el

        if not has_tts_key:
            _eng_name = "CLOVA" if st.session_state.tts_engine == "clova" else "ELEVENLABS"
            st.markdown(f'<div class="demo-banner">⚠️ {_eng_name} API 키 미설정 — Secrets에 API 키를 등록해주세요</div>', unsafe_allow_html=True)

        tts_output_path = os.path.join(TMPDIR, "tts_output.mp3")

        if st.button("🎙️ TTS 음성 생성"):
            with st.spinner("음성 생성 중..."):
                tts_success = False
                if st.session_state.tts_engine == "clova":
                    speaker = tts_voice.split(" - ")[0].strip()
                    tts_success = generate_tts_clova(st.session_state.script, tts_output_path,
                                                     speaker=speaker, speed=int((tts_speed - 1) * 5))
                    if tts_success:
                        st.success("✅ 클로바 TTS 완료!")
                    elif _has_clova:
                        st.error("클로바 TTS 실패")
                else:
                    vid = elevenlabs_voice_id or "21m00Tcm4TlvDq8ikWAM"
                    tts_success = generate_tts_elevenlabs(st.session_state.script, tts_output_path,
                                                          voice_id=vid, speed=tts_speed)
                    if tts_success:
                        st.success("✅ ElevenLabs TTS 완료!")
                    elif _has_el:
                        st.error("ElevenLabs TTS 실패")

                # API 키 없으면 데모 모드: 무음 mp3 생성
                if not tts_success and not has_tts_key:
                    silent_dur = max(15, target_dur)
                    if generate_silent_audio(silent_dur, tts_output_path):
                        tts_success = True
                        st.markdown('<div class="demo-banner">데모 모드: 무음 오디오가 생성되었습니다 (API 키 등록 시 실제 음성으로 교체됩니다)</div>', unsafe_allow_html=True)
                    else:
                        st.markdown('<div class="demo-banner">⚠️ TTS API 키가 없고 FFmpeg도 없어 음성을 생성할 수 없습니다</div>', unsafe_allow_html=True)

                if tts_success:
                    st.session_state.tts_done = True
                    st.audio(tts_output_path)
    else:
        st.info("위에서 스크립트를 먼저 생성해주세요.")

    # ── 자막 설정 & 생성 ──
    st.markdown("---")
    st.markdown('<div class="card"><div class="card-label">SUBTITLE</div><h3>📝 자막 생성</h3></div>', unsafe_allow_html=True)

    sub_c1, sub_c2, sub_c3 = st.columns(3)
    with sub_c1:
        sub_size = st.slider("자막 크기", 24, 72, 48)
        sub_pos = st.radio("위치", ["하단 중앙", "상단 중앙", "중앙"], horizontal=True)
    with sub_c2:
        sub_col = st.color_picker("텍스트 색상", "#FFFFFF")
        sub_bold = st.checkbox("굵게 (Bold)", value=True)
    with sub_c3:
        st.session_state.sub_animation = st.radio("애니메이션", ["없음", "페이드인/아웃"], horizontal=True)
        st.session_state.sub_margin = st.slider("세로 여백 (px)", 20, 200, 50)

    st.markdown('<div class="info-box">💡 ASS 자막: 외곽선 3px + 그림자 2px 자동 적용. 제품명·가격·할인 등 키워드는 노란색 하이라이트됩니다.</div>', unsafe_allow_html=True)

    if st.button("📝 스크립트 기반 자막 생성"):
        if st.session_state.script:
            lines = [l.strip() for l in st.session_state.script.split("\n") if l.strip()]
            subs = []
            t = 0.0
            for l in lines:
                d = max(1.5, len(l) * 0.25)
                subs.append({"start": round(t, 1), "end": round(t + d, 1), "text": l})
                t += d + 0.3

            tts_path = os.path.join(TMPDIR, "tts_output.mp3")
            if st.session_state.tts_done and os.path.exists(tts_path):
                tts_dur = get_audio_duration(tts_path)
                if tts_dur > 0:
                    raw_total = subs[-1]["end"] if subs else 0
                    if raw_total > 0:
                        ratio = tts_dur / raw_total
                        for s in subs:
                            s["start"] = round(s["start"] * ratio, 1)
                            s["end"] = round(s["end"] * ratio, 1)
                        st.info(f"TTS 음성 길이({tts_dur:.1f}초)에 맞춰 자막 타이밍이 자동 조정되었습니다.")

            st.session_state.sample_subs = subs
            st.session_state.subtitle_done = True

            fontpath = find_korean_font()
            pn_for_highlight = st.session_state.get("_w_pname", "") or st.session_state.get("_saved_pname", "") or st.session_state.coupang_product or ""
            ass_result = generate_ass_subtitle(
                subs, fontpath, product_name=pn_for_highlight,
                sub_size=sub_size, sub_pos=sub_pos, sub_col=sub_col,
                sub_bold=sub_bold, sub_anim=st.session_state.sub_animation,
                sub_margin=st.session_state.sub_margin
            )
            if ass_result:
                st.session_state.ass_path = ass_result
                st.success("✅ ASS 자막 생성 완료! (키워드 하이라이트 적용됨)")
            else:
                st.session_state.ass_path = ""
                st.success("✅ 자막 생성 완료! (ASS 파일 생성 실패 → drawtext fallback)")
        else:
            st.warning("위에서 스크립트를 먼저 생성해주세요.")

    if st.session_state.subtitle_done and st.session_state.sample_subs:
        st.markdown("**📋 자막 목록** — 직접 수정 가능")
        for i, sub in enumerate(st.session_state.sample_subs):
            sc1, sc2, sc3 = st.columns([2, 5, 0.6])
            with sc1:
                st.caption(f"{sub['start']}s → {sub['end']}s")
            with sc2:
                st.session_state.sample_subs[i]["text"] = st.text_input(f"sub{i}", value=sub["text"], label_visibility="collapsed", key=f"sub_{i}")
            with sc3:
                if st.button("🗑️", key=f"sdel_{i}"):
                    st.session_state.sample_subs.pop(i)
                    st.rerun()

    # ── BGM ──
    st.markdown("---")
    st.markdown('<div class="card"><div class="card-label">BGM</div><h3>🎵 BGM 배경 음악 (선택사항)</h3></div>', unsafe_allow_html=True)

    if not has_key("PIXABAY_API_KEY"):
        st.markdown('<div class="warn-box">⚠️ PIXABAY_API_KEY 미설정 — BGM 검색이 작동하지 않습니다. Secrets에 키를 등록하세요.</div>', unsafe_allow_html=True)

    bgm_c1, bgm_c2 = st.columns([3, 1])
    with bgm_c1:
        pcat_bgm = st.session_state.coupang_category or "기타"
        default_kw = BGM_CATEGORY_KEYWORDS.get(pcat_bgm, "upbeat positive")
        bgm_keyword = st.text_input("BGM 검색어", value=default_kw, placeholder="예: upbeat positive", key="bgm_kw_input")
    with bgm_c2:
        st.session_state.bgm_volume = st.slider("BGM 볼륨", 0.1, 0.4, st.session_state.bgm_volume, 0.05, key="bgm_vol_slider")

    if st.button("🎵 BGM 자동 검색", key="search_bgm"):
        with st.spinner("Pixabay에서 BGM 검색 중..."):
            results = search_pixabay_music(bgm_keyword, n=3)
            if results:
                st.session_state.bgm_results = results
                st.success(f"✅ {len(results)}개 BGM 후보 발견!")
            else:
                st.session_state.bgm_results = []
                st.warning("BGM 검색 실패 — API 키를 확인하거나 다른 키워드를 시도하세요. BGM 없이도 영상 제작이 가능합니다.")

    if st.session_state.bgm_results:
        for bi, bgm in enumerate(st.session_state.bgm_results):
            bc1, bc2, bc3 = st.columns([4, 1, 1])
            with bc1:
                title_str = bgm.get("title", "BGM")
                dur_str = f"{bgm.get('duration', 0)}초" if bgm.get("duration") else ""
                st.markdown(f"**🎵 {title_str}** &nbsp; {dur_str}")
                if bgm.get("tags"):
                    st.caption(bgm["tags"][:60])
            with bc2:
                if bgm.get("url"):
                    st.audio(bgm["url"])
            with bc3:
                is_selected = st.session_state.selected_bgm and str(bgm["id"]) in st.session_state.selected_bgm
                if is_selected:
                    st.markdown('<span class="badge badge-green">✓ 선택됨</span>', unsafe_allow_html=True)
                else:
                    if st.button("✅ 선택", key=f"sel_bgm_{bi}", use_container_width=True):
                        bgm_dir = _ensure_dir("shortform_bgm")
                        bgm_dest = bgm_dir / f"bgm_{bgm['id']}.mp3"
                        with st.spinner("BGM 다운로드 중..."):
                            if download_bgm(bgm["url"], str(bgm_dest)):
                                st.session_state.selected_bgm = str(bgm_dest)
                                st.success(f"✅ BGM 선택 완료!")
                                st.rerun()
                            else:
                                st.warning("BGM 다운로드 실패 — BGM 없이 진행 가능합니다.")

    if st.session_state.selected_bgm:
        st.markdown(f'<div class="info-box">🎵 선택된 BGM: <strong>{os.path.basename(st.session_state.selected_bgm)}</strong> (볼륨 {int(st.session_state.bgm_volume*100)}%)</div>', unsafe_allow_html=True)
        if st.button("🗑️ BGM 선택 해제", key="clear_bgm"):
            st.session_state.selected_bgm = ""
            st.rerun()

    # ── CTA 오버레이 ──
    st.markdown("---")
    st.markdown('<div class="card"><div class="card-label">CTA</div><h3>📢 CTA 오버레이 (선택사항)</h3></div>', unsafe_allow_html=True)
    st.markdown('<div class="info-box">💡 영상 마지막 N초에 클릭유도 문구(CTA)를 표시합니다. 비워두면 CTA 없이 영상이 생성됩니다.</div>', unsafe_allow_html=True)

    cta_cat = st.session_state.coupang_category or "기타"
    cta_candidates = CTA_LIBRARY.get(cta_cat, []) + CTA_COMMON
    seen_cta = set()
    cta_unique = []
    for c in cta_candidates:
        if c not in seen_cta:
            seen_cta.add(c)
            cta_unique.append(c)

    cta_c1, cta_c2 = st.columns([4, 2])
    with cta_c1:
        cta_select = st.selectbox("CTA 문구 선택", ["직접 입력"] + cta_unique, key="cta_selectbox",
                                   help=f"카테고리: {cta_cat} — 해당 카테고리 CTA + 공통 CTA")
        if cta_select == "직접 입력":
            st.session_state.cta_text = st.text_input("CTA 직접 입력", value=st.session_state.cta_text,
                                                       placeholder="예: 쿠팡에서 최저가 확인 👇", key="cta_custom_input")
        else:
            st.session_state.cta_text = cta_select
    with cta_c2:
        st.session_state.cta_position = st.radio("CTA 위치", ["상단", "하단", "중앙하단"], index=1,
                                                   horizontal=True, key="cta_pos_radio",
                                                   help="하단: 자막보다 위 / 상단: 화면 최상단 / 중앙하단: 화면 65%")
        st.session_state.cta_duration = st.slider("표시 시간 (마지막 N초)", 2, 10, st.session_state.cta_duration, key="cta_dur_slider")
        st.session_state.cta_color = st.color_picker("CTA 글자색", st.session_state.cta_color, key="cta_col_picker")

    if st.session_state.cta_text:
        st.markdown(f'<div class="info-box">📢 CTA: "<strong>{st.session_state.cta_text}</strong>" — 마지막 {st.session_state.cta_duration}초, {st.session_state.cta_position}</div>', unsafe_allow_html=True)

    # ── 최종 영상 조립 ──
    st.markdown("---")
    st.markdown('<div class="card"><div class="card-label">ASSEMBLE</div><h3>🎬 최종 영상 조립</h3></div>', unsafe_allow_html=True)

    has_clips = bool(st.session_state.clips)
    _hook_on = st.session_state.hook_test_enabled and has_clips
    _pi_on = st.session_state.pattern_interrupt_enabled
    _rb_on = st.session_state.retention_booster_enabled

    if not has_clips:
        st.info("STEP 1에서 클립을 먼저 추가해주세요")
    else:
        _opt_tags = []
        if _hook_on: _opt_tags.append("Hook A/B")
        if _pi_on: _opt_tags.append("PI")
        if _rb_on: _opt_tags.append("RB")
        _opt_str = " + ".join(_opt_tags) if _opt_tags else "기본"
        st.markdown(f"**{len(st.session_state.clips)}개 클립** · 목표 {target_dur}초 · {'TTS ✅' if st.session_state.tts_done else 'TTS 없음'} · 최적화: {_opt_str}")

        # Hook ON 시 Hook 텍스트 미리 생성
        if _hook_on:
            _hook_count = st.session_state.hook_version_count
            _pname = st.session_state.get("_w_pname", "") or st.session_state.get("_saved_pname", "") or st.session_state.coupang_product or "제품"
            _pcat = st.session_state.coupang_category or "기타"
            _cmode = st.session_state.content_mode or "클릭유도형"

            if st.button("🪝 Hook 텍스트 생성", key="gen_hooks"):
                with st.spinner("Hook A/B/C 텍스트 생성 중..."):
                    hooks = generate_hooks(_pname, _pcat, _cmode, _hook_count)
                    st.session_state.hook_versions = hooks
                    st.success(f"✅ {len(hooks)}개 Hook 생성 완료!")
                    st.rerun()

            if st.session_state.hook_versions:
                st.markdown("**🪝 Hook 텍스트 (수정 가능)**")
                for hi, hv in enumerate(st.session_state.hook_versions):
                    _hcol1, _hcol2 = st.columns([1, 5])
                    with _hcol1:
                        _type_badge = "badge-blue" if hv["name"] == "A" else ("badge-green" if hv["name"] == "B" else "badge-dark")
                        st.markdown(f'<span class="badge {_type_badge}">버전 {hv["name"]}</span>', unsafe_allow_html=True)
                        st.caption(hv["type"])
                    with _hcol2:
                        new_text = st.text_input(f"Hook {hv['name']}", value=hv["hook_text"], key=f"hook_edit_{hi}", label_visibility="collapsed")
                        st.session_state.hook_versions[hi]["hook_text"] = new_text

        if st.button("⚡ 영상 조립 시작", type="primary"):
            prog = st.progress(0)
            stat = st.empty()

            stat.text("📂 클립 확인 중...")
            prog.progress(10)

            valid = [c for c in st.session_state.clips if os.path.exists(c["path"])]
            if not valid:
                st.error("❌ 다운로드된 클립 파일이 없습니다. 영상을 먼저 다운로드해주세요.")
            else:
                tts_check = os.path.join(TMPDIR, "tts_output.mp3")
                tts_path = tts_check if st.session_state.tts_done and os.path.exists(tts_check) else None
                subs = st.session_state.sample_subs if st.session_state.subtitle_done else []
                ratio = "9:16" if "9:16" in crop_ratio else "1:1"
                ass_file = st.session_state.get("ass_path", "")
                bgm_file = st.session_state.get("selected_bgm", "")
                bgm_vol = st.session_state.get("bgm_volume", 0.2)
                cta_t = st.session_state.get("cta_text", "")
                cta_p = st.session_state.get("cta_position", "하단")
                cta_d = st.session_state.get("cta_duration", 3)
                cta_clr = st.session_state.get("cta_color", "#FFFFFF")

                if _hook_on and st.session_state.hook_versions:
                    # ═══ Hook A/B 테스트 모드: 버전별 영상 생성 ═══
                    _hook_count = len(st.session_state.hook_versions)
                    stat.text(f"🪝 Hook A/B 테스트: {_hook_count}개 버전 생성 시작...")
                    prog.progress(10)

                    with st.status(f"🪝 Hook {_hook_count}개 버전 생성 중...", expanded=True) as _hook_status:
                        for _hi, _hv in enumerate(st.session_state.hook_versions):
                            st.write(f"**버전 {_hv.get('name', chr(65+_hi))}** 생성 중... ({_hi+1}/{_hook_count})")
                        try:
                            hook_results = assemble_hook_versions(
                                valid, subs, tts_path, target_dur, crop_ratio=ratio,
                                ass_path=ass_file, bgm_path=bgm_file, bgm_volume=bgm_vol,
                                cta_text=cta_t, cta_position=cta_p, cta_duration=cta_d, cta_color=cta_clr,
                                hook_clip_path=None, hooks=st.session_state.hook_versions, hook_dur=3.0,
                                pattern_interrupt=_pi_on, retention_booster=_rb_on,
                                anti_shadowban=st.session_state.anti_shadowban_enabled
                            )
                            _hook_status.update(label=f"✅ Hook {_hook_count}개 버전 생성 완료!", state="complete")
                        except subprocess.TimeoutExpired:
                            st.error("⏱️ Hook 영상 생성 시간 초과 — 클립 수를 줄이거나 목표 길이를 짧게 설정해주세요.")
                            hook_results = []
                            _hook_status.update(label="❌ 시간 초과", state="error")
                        except Exception as e:
                            st.error(f"❌ Hook 영상 생성 중 오류: {e}")
                            hook_results = []
                            _hook_status.update(label="❌ 오류 발생", state="error")

                    st.session_state.hook_versions = hook_results
                    prog.progress(100)
                    stat.text("✅ 완료!")

                    success_count = sum(1 for h in hook_results if h.get("video_path"))
                    if success_count > 0:
                        st.success(f"🎉 Hook A/B 테스트 완료! {success_count}개 버전 생성 → STEP 4에서 비교/다운로드하세요.")
                        first_ok = next((h for h in hook_results if h.get("video_path")), None)
                        if first_ok:
                            st.session_state.output_path = first_ok["video_path"]
                    else:
                        if hook_results:
                            st.error("❌ 모든 Hook 버전 조립 실패")
                            for h in hook_results:
                                if h.get("error"):
                                    st.warning(f"버전 {h['name']}: {h['error']}")
                    # 임시파일 정리
                    _cleaned = cleanup_hook_temp_files()
                    if _cleaned > 0:
                        st.caption(f"🧹 임시 파일 {_cleaned}개 정리 완료")
                else:
                    # ═══ 기존 단일 영상 모드 (Hook OFF) — 100% 유지 ═══
                    stat.text(f"✂️ {len(valid)}개 클립 조립 중...")
                    prog.progress(30)

                    stat.text("🎬 FFmpeg 영상 합성 중... (최대 2분)")
                    prog.progress(50)

                    output, err_msg = assemble_video(valid, subs, tts_path, target_dur, ratio,
                                                      ass_path=ass_file, bgm_path=bgm_file, bgm_volume=bgm_vol,
                                                      cta_text=cta_t, cta_position=cta_p,
                                                      cta_duration=cta_d, cta_color=cta_clr,
                                                      pattern_interrupt=_pi_on,
                                                      retention_booster=_rb_on,
                                                      anti_shadowban=st.session_state.anti_shadowban_enabled)

                    if output and os.path.exists(output):
                        prog.progress(100)
                        stat.text("✅ 완료!")
                        st.session_state.output_path = output
                        st.success("🎉 영상 조립 완료! STEP 4에서 다운로드하세요.")
                        st.video(output)
                    else:
                        prog.progress(100)
                        st.error(f"❌ 영상 생성에 실패했습니다. 클립이 너무 짧거나 없을 수 있어요. ({err_msg or '알 수 없는 오류'})")

    # ═══════════════════════════════════════════════════════════════
    # Multi-Video Generator (영상 5개 한번에 생성)
    # ═══════════════════════════════════════════════════════════════
    st.markdown("---")
    st.markdown('<div class="ux-card"><div class="ux-card-title">MULTI-VIDEO</div><h4>🎬 Multi-Video 생성</h4><p class="ux-sub">현재 템플릿 × Hook A/B/C × Pattern Interrupt ON/OFF → 영상 5개 한번에 생성</p></div>', unsafe_allow_html=True)

    _mv_pname = st.session_state.get("_w_pname", "") or st.session_state.get("_saved_pname", "") or st.session_state.coupang_product or ""
    _mv_clips = [c for c in st.session_state.clips if os.path.exists(c.get("path", ""))]

    if not _mv_clips:
        st.markdown('<div class="warn-box">⚠️ STEP 1에서 클립을 먼저 추가해주세요.</div>', unsafe_allow_html=True)
    elif not _mv_pname:
        st.markdown('<div class="warn-box">⚠️ STEP 1에서 제품명을 먼저 입력해주세요.</div>', unsafe_allow_html=True)
    else:
        # 현재 선택된 템플릿 기반으로 조합 생성
        _mv_cur_tpl = st.session_state.get("active_template", "coupang_shorts") or "coupang_shorts"
        _mv_tpl_name = TEMPLATES.get(_mv_cur_tpl, {}).get("name", _mv_cur_tpl)
        _mv_combos = [
            {"template": _mv_cur_tpl, "hook_type": "A", "hook_label": "문제 제시형", "pi": False, "label": f"{_mv_tpl_name} + Hook A"},
            {"template": _mv_cur_tpl, "hook_type": "B", "hook_label": "놀람형",     "pi": False, "label": f"{_mv_tpl_name} + Hook B"},
            {"template": _mv_cur_tpl, "hook_type": "C", "hook_label": "손해 회피형", "pi": False, "label": f"{_mv_tpl_name} + Hook C"},
            {"template": _mv_cur_tpl, "hook_type": "A", "hook_label": "문제 제시형", "pi": True,  "label": f"{_mv_tpl_name} + Hook A + PI"},
            {"template": _mv_cur_tpl, "hook_type": "B", "hook_label": "놀람형",     "pi": True,  "label": f"{_mv_tpl_name} + Hook B + PI"},
        ]

        with st.expander("📋 생성될 영상 5개 조합", expanded=False):
            for _mvi, _mvc in enumerate(_mv_combos):
                _pi_tag = " + Pattern Interrupt ✅" if _mvc["pi"] else ""
                st.markdown(f"**영상 {_mvi+1}** — {_mvc['label']}{_pi_tag} ({_mvc['hook_label']})")

        if st.button("⚡ 영상 5개 한번에 생성", key="btn_multi_video", type="primary", use_container_width=True):
            _mv_target_dur = st.session_state.get("_w_target_dur", 30)
            _mv_crop = st.session_state.get("_w_crop_ratio", "9:16 세로형 (숏폼)")
            _mv_ratio = "9:16" if "9:16" in _mv_crop else "1:1"
            _mv_tts_check = os.path.join(TMPDIR, "tts_output.mp3")
            _mv_tts_path = _mv_tts_check if st.session_state.tts_done and os.path.exists(_mv_tts_check) else None
            _mv_subs = st.session_state.sample_subs if st.session_state.subtitle_done else []
            _mv_ass = st.session_state.get("ass_path", "")
            _mv_bgm = st.session_state.get("selected_bgm", "")
            _mv_bgm_vol = st.session_state.get("bgm_volume", 0.2)
            _mv_pcat = st.session_state.coupang_category or "기타"
            _mv_cmode = st.session_state.content_mode or "클릭유도형"

            _mv_results = []
            _mv_out_dir = _ensure_dir("multi_video_output")

            with st.status("🎬 Multi-Video 5개 생성 중...", expanded=True) as _mv_status:
                for _mvi, _mvc in enumerate(_mv_combos):
                    st.write(f"**영상 {_mvi+1} / 5** 생성 중 — {_mvc['label']}...")

                    # 1. 해당 템플릿의 설정 가져오기
                    _mv_tpl = TEMPLATES.get(_mvc["template"], {})
                    import random as _mv_rnd
                    _mv_cta_cat = st.session_state.coupang_category or "기타"
                    _mv_cta_pool = CTA_LIBRARY.get(_mv_cta_cat, CTA_LIBRARY.get("기타", [])) + CTA_COMMON
                    _mv_cta_text = _mv_rnd.choice(_mv_cta_pool) if _mv_cta_pool else _mv_tpl.get("cta_text", "")
                    _mv_cta_color = _mv_tpl.get("sub_color", st.session_state.get("cta_color", "#FFFFFF"))
                    _mv_cta_pos = _mv_tpl.get("cta_position", "하단")
                    _mv_cta_dur = st.session_state.get("cta_duration", 3)
                    _mv_pi = _mvc.get("pi", _mv_tpl.get("pattern_interrupt", False))
                    _mv_rb = _mv_tpl.get("retention_booster", True)

                    # 2. Hook 텍스트 생성
                    _hook_map = {"A": "문제 제시형", "B": "놀람형", "C": "손해 회피형"}
                    _mv_hooks = generate_hooks(_mv_pname, _mv_pcat, _mv_cmode, count=3)
                    _hook_idx = {"A": 0, "B": 1, "C": 2}.get(_mvc["hook_type"], 0)
                    _mv_hook = [_mv_hooks[min(_hook_idx, len(_mv_hooks)-1)]] if _mv_hooks else []

                    if not _mv_hook:
                        _mv_hook = [{"name": _mvc["hook_type"], "type": _mvc["hook_label"],
                                     "hook_text": f"{_mv_pname} 지금 확인하세요"}]

                    # 3. assemble_hook_versions로 영상 생성 (Hook 1개만 = 단일 영상)
                    try:
                        _mv_ver_results = assemble_hook_versions(
                            _mv_clips, _mv_subs, _mv_tts_path, _mv_target_dur,
                            crop_ratio=_mv_ratio, ass_path=_mv_ass,
                            bgm_path=_mv_bgm, bgm_volume=_mv_bgm_vol,
                            cta_text=_mv_cta_text, cta_position=_mv_cta_pos,
                            cta_duration=_mv_cta_dur, cta_color=_mv_cta_color,
                            hook_clip_path=None, hooks=_mv_hook, hook_dur=3.0,
                            pattern_interrupt=_mv_pi, retention_booster=_mv_rb,
                            anti_shadowban=st.session_state.anti_shadowban_enabled
                        )
                    except Exception as _mv_err:
                        _mv_ver_results = []
                        st.write(f"⚠️ 영상 {_mvi+1} 생성 실패: {_mv_err}")

                    # 4. 결과 저장 — 고유 파일명으로 복사
                    if _mv_ver_results and _mv_ver_results[0].get("video_path") and os.path.exists(_mv_ver_results[0]["video_path"]):
                        import shutil
                        _mv_pi_tag = "_PI" if _mvc.get("pi") else ""
                        _mv_final_name = f"multi_video_{_mvi+1}_hook{_mvc['hook_type']}{_mv_pi_tag}.mp4"
                        _mv_final_path = str(_mv_out_dir / _mv_final_name)
                        shutil.copy2(_mv_ver_results[0]["video_path"], _mv_final_path)
                        _mv_results.append({
                            "name": f"video_{_mvi+1}",
                            "template": TEMPLATES.get(_mvc["template"], {}).get("name", _mvc["template"]),
                            "template_key": _mvc["template"],
                            "hook_type": _mvc["hook_type"],
                            "hook_label": _mvc["hook_label"],
                            "hook_text": _mv_ver_results[0].get("hook_text", ""),
                            "video_path": _mv_final_path,
                            "subtitle_path": _mv_ver_results[0].get("subtitle_path", ""),
                            "audio_path": _mv_ver_results[0].get("audio_path", ""),
                            "label": _mvc["label"],
                            "pi": _mvc.get("pi", False),
                        })
                    else:
                        _mv_results.append({
                            "name": f"video_{_mvi+1}",
                            "template": TEMPLATES.get(_mvc["template"], {}).get("name", _mvc["template"]),
                            "template_key": _mvc["template"],
                            "hook_type": _mvc["hook_type"],
                            "hook_label": _mvc["hook_label"],
                            "hook_text": "",
                            "video_path": "",
                            "subtitle_path": "",
                            "audio_path": "",
                            "label": _mvc["label"],
                            "pi": _mvc.get("pi", False),
                            "error": "생성 실패",
                        })

                _mv_success = sum(1 for r in _mv_results if r.get("video_path"))
                _mv_status.update(label=f"✅ Multi-Video {_mv_success}/5개 생성 완료!", state="complete" if _mv_success > 0 else "error")

            st.session_state.multi_video_outputs = _mv_results

            if _mv_success > 0:
                st.success(f"🎉 Multi-Video {_mv_success}/5개 생성 완료! → STEP 4에서 다운로드하세요.")
                # 첫 번째 성공한 영상을 output_path에도 설정
                _first_mv = next((r for r in _mv_results if r.get("video_path")), None)
                if _first_mv:
                    st.session_state.output_path = _first_mv["video_path"]
            else:
                st.error("❌ 모든 영상 생성에 실패했습니다.")

            # 임시파일 정리
            _cleaned = cleanup_hook_temp_files()
            if _cleaned > 0:
                st.caption(f"🧹 임시 파일 {_cleaned}개 정리 완료")

    _render_nav_buttons()


# ═════════════════════════════════════════════════════════════════
# render_step4: ⬇️ 미리보기 + 다운로드
# ═════════════════════════════════════════════════════════════════
def render_step4():
    st.markdown('<div class="ux-card"><div class="ux-card-title">STEP 04</div><h4>🔗 추적 링크 + 다운로드</h4><p class="ux-sub">영상별 매출 추적 subId 생성 → 해시태그/설명 → 다운로드. <strong>해자: 다른 도구는 여기가 없다.</strong></p></div>', unsafe_allow_html=True)

    if not has_key("ANTHROPIC_API_KEY"):
        st.markdown('<div class="demo-banner">⚠️ ANTHROPIC_API_KEY 미설정 — AI 기능이 작동하지 않습니다</div>', unsafe_allow_html=True)

    # ── 해시태그 20개 ──
    if st.session_state.coupang_product:
        pname = st.session_state.coupang_product
        pcat = st.session_state.coupang_category

        st.markdown("#### 1️⃣ 해시태그 자동 생성 (AI + DB)")
        st.markdown('<div class="info-box">AI 맞춤 10개 + 카테고리 DB 5개 + 공통 필수 5개 = 총 20개 해시태그를 생성합니다.</div>', unsafe_allow_html=True)

        if st.button("✨ 해시태그 20개 생성", key="gen_hashtags", disabled=not has_key("ANTHROPIC_API_KEY")):
            with st.spinner("AI 해시태그 생성 + 카테고리 DB 조합 중..."):
                cmode = st.session_state.content_mode
                result = call_claude(
                    "SNS 해시태그 전문가. 해시태그만 출력. # 붙여서 공백으로 구분. 딱 10개만.",
                    f"제품: {pname}\n카테고리: {pcat}\n콘텐츠 목적: {cmode}\n\n이 제품에 최적화된 해시태그 10개를 만들어줘.\n조건:\n- 제품 특성에 맞는 검색량 높은 키워드\n- '{cmode}' 목적에 맞는 태그 포함\n- #shorts #fyp #viral 중 2개 포함\n- 모두 # 붙여서 공백으로 구분\n- 딱 10개만 출력"
                )
                if result:
                    ai_tags = [t.strip() for t in result.strip().split() if t.strip().startswith("#")][:10]

                    cat_pool = CATEGORY_HASHTAGS.get(pcat, CATEGORY_HASHTAGS["기타"])
                    cat_available = [t for t in cat_pool if t not in ai_tags]
                    import random as _rnd
                    cat_tags = _rnd.sample(cat_available, min(5, len(cat_available)))

                    common_tags = [t for t in COMMON_HASHTAGS if t not in ai_tags and t not in cat_tags]

                    all_tags = []
                    seen_tags = set()
                    for t in common_tags + ai_tags + cat_tags:
                        if t not in seen_tags:
                            all_tags.append(t)
                            seen_tags.add(t)
                    all_tags = all_tags[:20]
                    _rnd.shuffle(all_tags)

                    st.session_state.hashtag_list = all_tags
                    st.session_state.hashtag_selections = {t: True for t in all_tags}
                    st.session_state.coupang_hashtags = " ".join(all_tags)
                    st.rerun()
                else:
                    st.markdown('<div class="demo-banner">⚠️ API 키 없음 — 데모 모드에서는 생성되지 않습니다</div>', unsafe_allow_html=True)

        if st.session_state.hashtag_list:
            st.markdown("**해시태그 선택** — 체크박스로 포함/제외 가능")

            ht_btn1, ht_btn2, ht_btn3 = st.columns(3)
            with ht_btn1:
                if st.button("✅ 전체 선택", key="ht_all"):
                    st.session_state.hashtag_selections = {t: True for t in st.session_state.hashtag_list}
                    st.rerun()
            with ht_btn2:
                if st.button("⬜ 전체 해제", key="ht_none"):
                    st.session_state.hashtag_selections = {t: False for t in st.session_state.hashtag_list}
                    st.rerun()
            with ht_btn3:
                selected_tags = [t for t in st.session_state.hashtag_list if st.session_state.hashtag_selections.get(t, True)]
                st.metric("선택됨", f"{len(selected_tags)}개")

            tag_cols_per_row = 4
            for row_start in range(0, len(st.session_state.hashtag_list), tag_cols_per_row):
                row_tags = st.session_state.hashtag_list[row_start:row_start+tag_cols_per_row]
                ht_cols = st.columns(tag_cols_per_row)
                for col_idx, tag in enumerate(row_tags):
                    with ht_cols[col_idx]:
                        label = f"{tag} 🔒" if tag in COMMON_HASHTAGS else tag
                        checked = st.session_state.hashtag_selections.get(tag, True)
                        st.session_state.hashtag_selections[tag] = st.checkbox(label, value=checked, key=f"ht_{tag}")

            selected_tags = [t for t in st.session_state.hashtag_list if st.session_state.hashtag_selections.get(t, True)]
            st.session_state.coupang_hashtags = " ".join(selected_tags)
            st.markdown("**📋 복사용 (선택된 해시태그):**")
            st.code(st.session_state.coupang_hashtags, language=None)

        st.markdown("---")

        # ── 설명란 자동 생성 ──
        st.markdown("#### 2️⃣ 유튜브 / 인스타 설명란 자동 생성")
        if st.button("✨ 설명란 자동 생성", key="gen_desc", disabled=not has_key("ANTHROPIC_API_KEY")):
            with st.spinner("설명란 생성 중..."):
                aff_link = st.session_state.coupang_affiliate_link
                link_instruction = ""
                if aff_link:
                    link_instruction = f"\n\n중요: 아래 쿠팡 파트너스 링크를 설명란에 반드시 포함해줘:\n{aff_link}\n유튜브 설명란에는 '쿠팡에서 확인하기 👇' 바로 아래에, 인스타 설명란에는 '프로필 링크' 대신 이 링크를 넣어줘."
                result = call_claude(
                    "SNS 마케팅 카피라이터. 설명란만 출력.",
                    f"제품: {pname}\n카테고리: {pcat}\n해시태그: {st.session_state.coupang_hashtags}\n\n유튜브 쇼츠 + 인스타 릴스용 설명란을 각각 작성해줘.\n\n[유튜브 설명란]\n- 제품 한줄 소개\n- '쿠팡에서 확인하기 👇' (링크 자리)\n- 해시태그\n\n[인스타 설명란]\n- 감성적 한줄 + 이모지\n- 제품 특징 3줄\n- '프로필 링크에서 확인하세요 🔗'\n- 해시태그{link_instruction}"
                )
                if result:
                    st.session_state.coupang_desc = result
                else:
                    st.markdown('<div class="demo-banner">⚠️ API 키 없음 — 데모 모드에서는 생성되지 않습니다</div>', unsafe_allow_html=True)

        if st.session_state.coupang_desc:
            st.code(st.session_state.coupang_desc, language=None)

        st.markdown("---")
    else:
        st.info("STEP 1에서 쿠팡 제품을 먼저 등록하세요.")
        st.markdown("---")

    # ── 🔗 추적 링크 자동 생성 (Phase 1-B 해자) ──
    st.markdown("#### 🔗 추적 링크 자동 생성")
    st.markdown('<div class="info-box">영상마다 고유한 <strong>추적 ID(subId)</strong>를 부여해 어떤 영상이 매출 냈는지 추적합니다. 다른 도구는 영상만 만들고 끝, 우리는 매출까지 봅니다.</div>', unsafe_allow_html=True)

    _track_pid = st.session_state.active_project_id
    _track_url_default = st.session_state.coupang_affiliate_link or st.session_state.get("_last_coupang_url", "")
    _track_url = st.text_input(
        "추적할 쿠팡 URL (상품 URL 또는 기존 파트너스 링크)",
        value=_track_url_default,
        key="tracking_url_input",
        placeholder="https://www.coupang.com/vp/products/..."
    )

    _track_c1, _track_c2 = st.columns([1, 1])
    with _track_c1:
        _gen_track = st.button("🎯 이 영상용 추적 링크 생성", key="btn_gen_tracking", type="primary", use_container_width=True)
    with _track_c2:
        _has_partners_keys = bool(get_api_key("COUPANG_PARTNERS_ACCESS_KEY")) and bool(get_api_key("COUPANG_PARTNERS_SECRET_KEY"))
        if _has_partners_keys:
            st.success("✅ 쿠팡 Partners API 키 감지 — deeplink 자동 생성")
        else:
            st.info("ℹ️ Partners API 키 없음 — subId만 생성 후 수동 적용 안내")

    if _gen_track:
        if not _track_pid:
            st.error("❌ 활성 프로젝트가 없습니다. 먼저 프로젝트를 생성/선택하세요.")
        elif not _track_url.strip():
            st.error("❌ 쿠팡 URL을 입력하세요.")
        else:
            sub_id = tracking.generate_video_subid()
            ak = get_api_key("COUPANG_PARTNERS_ACCESS_KEY")
            sk = get_api_key("COUPANG_PARTNERS_SECRET_KEY")
            with st.spinner("추적 링크 생성 중..."):
                deeplink_result = tracking.create_partners_deeplink(_track_url.strip(), sub_id, ak, sk)
            _video_id_for_track = (
                st.session_state.get("output_path", "")
                or f"manual_{int(time.time()*1000)}"
            )
            _vid_basename = os.path.basename(_video_id_for_track) if _video_id_for_track else f"manual_{sub_id}"
            _record = tracking.make_tracking_record(
                video_id=_vid_basename,
                project_id=_track_pid,
                coupang_url=_track_url.strip(),
                deeplink_result=deeplink_result if deeplink_result.get("ok") else {"subId": sub_id},
                template=st.session_state.get("active_template", ""),
                title=st.session_state.coupang_product or "",
            )
            project_store.add_tracking_record(_track_pid, _record)
            st.session_state["_last_tracking_record"] = _record
            st.session_state["_last_tracking_result"] = deeplink_result
            st.rerun()

    _last_rec = st.session_state.get("_last_tracking_record")
    _last_res = st.session_state.get("_last_tracking_result")
    if _last_rec:
        if _last_res and _last_res.get("ok"):
            st.success(f"✅ 추적 링크 생성 완료! subId: `{_last_rec['sub_id']}`")
            st.markdown("**🔗 단축 링크 (영상 설명란에 붙여넣기):**")
            st.code(_last_rec["shorten_url"] or _last_res.get("shortenUrl", ""), language=None)
            with st.expander("기술 상세 (랜딩 URL / subId)"):
                st.code(f"subId        : {_last_rec['sub_id']}\nshortenUrl   : {_last_rec['shorten_url']}\nlandingUrl   : {_last_rec['landing_url']}\noriginalUrl  : {_last_rec['original_url']}", language="text")
        else:
            st.warning(f"⚠️ Partners API 실패 또는 키 미설정 → 수동 적용 모드: `{_last_rec['sub_id']}`")
            if _last_res and _last_res.get("error"):
                st.caption(f"사유: {_last_res['error']}")
            st.markdown(tracking.manual_subid_instructions(_last_rec["sub_id"]))

    _all_records = project_store.list_tracking_records(_track_pid) if _track_pid else []
    if _all_records:
        with st.expander(f"📋 이 프로젝트 추적 레코드 ({len(_all_records)}개)"):
            for _r in reversed(_all_records[-10:]):
                _short = _r.get("shorten_url") or "(키 없음 — 수동 적용)"
                st.markdown(f"- **{_r.get('sub_id', '')}** · {_r.get('title', '')} · {_r.get('created_at', '')[:19]}  \n  → {_short}")

    st.markdown("---")

    # ── 썸네일 자동 생성 ──
    st.markdown("#### 3️⃣ 썸네일 반자동 생성")
    st.markdown('<div class="card"><div class="card-label">THUMBNAIL</div><h3>🖼️ 썸네일 반자동 생성</h3></div>', unsafe_allow_html=True)
    st.markdown('<div class="info-box">3가지 템플릿 + 2가지 해상도로 썸네일을 자동 생성합니다. 제품 이미지가 있으면 자동으로 활용됩니다.</div>', unsafe_allow_html=True)

    pn = st.session_state.get("_w_pname", "") or st.session_state.get("_saved_pname", "") or st.session_state.coupang_product or "제품"

    th_c1, th_c2 = st.columns(2)
    with th_c1:
        thumb_template = st.radio("템플릿", ["임팩트형", "가격강조형", "문제해결형"], horizontal=True, key="thumb_tmpl",
                                  help="임팩트형: 어두운 배경+큰 텍스트 / 가격강조형: 주황 배경+가격 강조 / 문제해결형: Before→After")
    with th_c2:
        thumb_res = st.radio("해상도", ["유튜브 (1280x720)", "인스타 (1080x1080)", "둘 다"], horizontal=True, key="thumb_res")

    default_main = ""
    if st.session_state.selected_title:
        default_main = st.session_state.selected_title
    elif st.session_state.generated_titles:
        default_main = st.session_state.generated_titles[0].get("text", "")
    elif pn and pn != "제품":
        default_main = pn

    thumb_main = st.text_input("메인 텍스트", value=default_main, placeholder="예: 이거 안 쓰면 손해!", key="thumb_main")
    thumb_sub = st.text_input("서브 텍스트 (선택)", placeholder="예: 쿠팡 최저가 확인하기", key="thumb_sub")

    if st.button("🖼️ 썸네일 생성", key="gen_thumb"):
        if not thumb_main:
            st.warning("메인 텍스트를 입력해주세요.")
        else:
            with st.spinner("썸네일 생성 중..."):
                prod_img = _get_first_product_image()
                resolutions = []
                if "유튜브" in thumb_res or "둘 다" in thumb_res:
                    resolutions.append(("유튜브", (1280, 720)))
                if "인스타" in thumb_res or "둘 다" in thumb_res:
                    resolutions.append(("인스타", (1080, 1080)))

                generated = []
                for label, res in resolutions:
                    result = generate_thumbnail(thumb_template, res, thumb_main, thumb_sub, prod_img)
                    if result:
                        generated.append({"label": label, "w": res[0], "h": res[1], "path": result})

                if generated:
                    st.session_state.thumbnail_paths = generated
                    st.success(f"✅ 썸네일 {len(generated)}개 생성 완료!")
                    if not find_korean_font():
                        st.markdown('<div class="warn-box">⚠️ 한글 폰트 미감지: 한글이 깨져 보일 수 있습니다. Streamlit Cloud의 경우 packages.txt에 fonts-nanum이 필요합니다.</div>', unsafe_allow_html=True)
                else:
                    st.error("썸네일 생성 실패 — Pillow 라이브러리를 확인해주세요.")

    if st.session_state.thumbnail_paths:
        thumb_cols = st.columns(len(st.session_state.thumbnail_paths))
        for i, td in enumerate(st.session_state.thumbnail_paths):
            with thumb_cols[i]:
                st.markdown(f'<span class="badge badge-blue">{td["label"]} ({td["w"]}x{td["h"]})</span>', unsafe_allow_html=True)
                if os.path.exists(td["path"]):
                    st.image(td["path"], use_container_width=True)
                    with open(td["path"], "rb") as f:
                        st.download_button(f"⬇️ {td['label']} 다운로드", data=f.read(),
                                           file_name=f"thumbnail_{td['label']}_{td['w']}x{td['h']}.png",
                                           mime="image/png", use_container_width=True, key=f"dl_thumb_{i}")

    st.markdown("---")

    # ── 완성 영상 다운로드 ──
    st.markdown('<div class="card"><div class="card-label">DOWNLOAD</div><h3>💾 완성 영상 다운로드</h3></div>', unsafe_allow_html=True)

    pn = st.session_state.get("_w_pname", "") or st.session_state.get("_saved_pname", "") or st.session_state.coupang_product or "제품"
    aff_link = st.session_state.coupang_affiliate_link

    dc1, dc2 = st.columns(2)
    with dc1:
        auto_title = st.text_input("제목", value=f"{pn} 리뷰 | 이거 진짜 괜찮네요 #shorts")
    with dc2:
        auto_tags = st.text_input("해시태그", value=st.session_state.coupang_hashtags or f"#{pn} #숏폼 #리뷰 #shorts #viral #fyp")

    _pd = st.session_state.get("_w_pdesc", "") or ""
    desc_base = st.session_state.coupang_desc or _pd
    if aff_link and aff_link not in desc_base:
        desc_default = f"{desc_base}\n\n🛒 쿠팡에서 확인하기 👇\n{aff_link}\n\n{auto_tags}"
    else:
        desc_default = f"{desc_base}\n\n{auto_tags}" if desc_base else auto_tags
    auto_desc = st.text_area("설명", value=desc_default, height=100)

    if aff_link:
        st.markdown(f'<div class="info-box">🔗 쿠팡 파트너스 링크가 설명란에 자동 포함되었습니다.</div>', unsafe_allow_html=True)

    # ═══════════════════════════════════════════════════════════════
    # 결과 표시 우선순위: Multi-Video > Hook A/B > 단일 영상
    # ═══════════════════════════════════════════════════════════════

    _mv_outputs = st.session_state.get("multi_video_outputs", [])
    _mv_has_videos = any(r.get("video_path") and os.path.exists(r.get("video_path", "")) for r in _mv_outputs)
    _hook_versions = st.session_state.get("hook_versions", [])
    _hook_has_videos = any(h.get("video_path") and os.path.exists(h.get("video_path", "")) for h in _hook_versions)
    _single_ready = st.session_state.get("output_path") and os.path.exists(st.session_state.get("output_path", ""))

    # ── 1순위: Multi-Video 결과 ──
    if _mv_has_videos:
        _mv_success = [r for r in _mv_outputs if r.get("video_path") and os.path.exists(r.get("video_path", ""))]
        st.markdown(f"### 🎬 Multi-Video 결과 ({len(_mv_success)}/5개)")
        st.markdown('<div class="info-box">현재 템플릿 × Hook A/B/C × PI ON/OFF 조합 영상 5개입니다. 각 영상을 플랫폼별로 다운로드하세요!</div>', unsafe_allow_html=True)

        for _mvi, _mvr in enumerate(_mv_outputs):
            _tpl_badge = "badge-blue"
            if "쿠팡" in _mvr.get("template", ""): _tpl_badge = "badge-red"
            elif "틱톡" in _mvr.get("template", ""): _tpl_badge = "badge-green"
            elif "문제" in _mvr.get("template", ""): _tpl_badge = "badge-dark"

            _pi_label = " · PI ✅" if _mvr.get("pi") else ""
            st.markdown(f'<div class="card" style="margin-bottom:12px;"><span class="badge {_tpl_badge}">영상 {_mvi+1}</span> &nbsp; <strong>{_mvr.get("label", "")}{_pi_label}</strong></div>', unsafe_allow_html=True)

            if _mvr.get("video_path") and os.path.exists(_mvr["video_path"]):
                _mv_vc1, _mv_vc2 = st.columns([2, 3])
                with _mv_vc1:
                    st.video(_mvr["video_path"])
                with _mv_vc2:
                    st.markdown(f"**템플릿:** {_mvr.get('template', '')}")
                    st.markdown(f"**Hook:** {_mvr.get('hook_type', '')} ({_mvr.get('hook_label', '')})")
                    if _mvr.get("pi"):
                        st.markdown("**Pattern Interrupt:** ✅ ON")
                    if _mvr.get("hook_text"):
                        st.caption(f'"{_mvr["hook_text"]}"')
                    # 플랫폼별 다운로드
                    _mv_dl_cols = st.columns(3)
                    for _pi, (platform, p_icon) in enumerate([("유튜브", "▶"), ("인스타", "📸"), ("틱톡", "🎵")]):
                        with _mv_dl_cols[_pi]:
                            with open(_mvr["video_path"], "rb") as f:
                                st.download_button(
                                    f"{p_icon} {platform}",
                                    data=f.read(),
                                    file_name=f"{pn}_mv{_mvi+1}_{platform}.mp4",
                                    mime="video/mp4",
                                    use_container_width=True,
                                    key=f"dl_mv_{_mvi}_{platform}"
                                )
            elif _mvr.get("error"):
                st.warning(f"⚠️ 영상 {_mvi+1} 생성 실패: {_mvr['error']}")
        st.markdown("---")

    # ── 2순위: Hook A/B 테스트 결과 ──
    if st.session_state.hook_test_enabled and _hook_has_videos:
        st.markdown("### 🪝 Hook A/B 테스트 결과")
        st.markdown('<div class="info-box">같은 제품, 첫 3초만 다른 영상입니다. 성과를 비교해보세요!</div>', unsafe_allow_html=True)

        _hook_cols = st.columns(len(_hook_versions))
        for hi, hv in enumerate(_hook_versions):
            with _hook_cols[hi]:
                _ver_badge = "badge-blue" if hv["name"] == "A" else ("badge-green" if hv["name"] == "B" else "badge-dark")
                st.markdown(f'<span class="badge {_ver_badge}">버전 {hv["name"]}</span> <strong>{hv["type"]}</strong>', unsafe_allow_html=True)
                st.caption(f'"{hv["hook_text"]}"')

                if hv.get("video_path") and os.path.exists(hv["video_path"]):
                    st.video(hv["video_path"])
                    # 플랫폼별 다운로드
                    for platform, p_badge in [("유튜브", "badge-dark"), ("인스타", "badge-blue"), ("틱톡", "badge-green")]:
                        with open(hv["video_path"], "rb") as f:
                            st.download_button(
                                f"⬇️ {platform}",
                                data=f.read(),
                                file_name=f"{pn}_hook_{hv['name']}_{platform}.mp4",
                                mime="video/mp4",
                                use_container_width=True,
                                key=f"dl_hook_{hv['name']}_{platform}"
                            )
                elif hv.get("error"):
                    st.error(f"❌ {hv['error']}")
                else:
                    st.warning("영상 없음")
        st.markdown("---")

    # ── 3순위: 플랫폼별 다운로드 (단일 영상) ──
    st.markdown("### 📥 플랫폼별 다운로드")

    if not _single_ready:
        st.markdown('<div class="warn-box">⚠️ STEP 3에서 영상 조립을 먼저 완료해주세요.</div>', unsafe_allow_html=True)

    specs = [
        ("▶ 유튜브 쇼츠", "1080×1920 · MP4", "badge-dark", f"{pn}_youtube_shorts.mp4"),
        ("📸 인스타 릴스", "1080×1920 · MP4", "badge-blue", f"{pn}_instagram_reels.mp4"),
        ("🎵 틱톡", "1080×1920 · MP4", "badge-green", f"{pn}_tiktok.mp4"),
    ]
    for name, spec, badge, fn in specs:
        si1, si2 = st.columns([4, 1])
        with si1:
            st.markdown(f'<div class="card" style="margin-bottom:8px;"><strong>{name}</strong> &nbsp; <span class="badge {badge}">{spec}</span></div>', unsafe_allow_html=True)
        with si2:
            if _single_ready:
                with open(st.session_state.output_path, "rb") as f:
                    st.download_button("⬇️ 다운로드", data=f.read(), file_name=fn, mime="video/mp4", use_container_width=True, key=f"dl_{name}")
            else:
                st.button("⬇️ 다운로드", disabled=True, use_container_width=True, key=f"dld_{name}")

    st.markdown("---")
    with st.expander("🔑 필요한 API 키 안내"):
        st.code("""
# Streamlit Cloud → Settings → Secrets 에 입력
ANTHROPIC_API_KEY = "sk-ant-..."     # AI 스크립트/자막
ELEVENLABS_API_KEY = "sk_..."        # TTS 음성합성
PEXELS_API_KEY = "..."               # 무료 영상 검색
PIXABAY_API_KEY = "..."              # BGM 음악 검색

# (선택) 클로바 TTS
CLOVA_TTS_CLIENT_ID = "..."
CLOVA_TTS_CLIENT_SECRET = "..."
        """, language="toml")

    # STEP 4는 마지막이므로 이전 버튼만
    st.markdown("---")
    nav_prev, _, _ = st.columns([1, 3, 1])
    with nav_prev:
        if st.button("← 이전 단계", key="prev_4"):
            st.session_state.current_step = 3
            st.rerun()


# ═════════════════════════════════════════════════════════════════
# 사이드바 — 사용자 식별 + 관리자 메뉴 (Founder만)
# ═════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("### 👤 내 계정")
    _sb_uid = st.text_input(
        "user_id (이메일)",
        value=st.session_state.get("user_id", ""),
        key="_sidebar_user_id",
        placeholder="you@example.com",
        help="처음 입력한 사람이 자동으로 Founder가 됩니다.",
    )
    if _sb_uid != st.session_state.get("user_id", ""):
        st.session_state.user_id = _sb_uid

    # 첫 사용자 자동 founder claim (file에 founder 없을 때)
    if _sb_uid and not whitelist._load_founders_file().get("founders"):
        _claim = whitelist.claim_first_founder(_sb_uid)
        if _claim["ok"]:
            st.success(f"👑 첫 Founder로 등록되었습니다: {_sb_uid}")

    if _sb_uid:
        _tier = whitelist.user_tier(_sb_uid)
        _tier_emoji = {
            "founder": "👑 Founder",
            "invitee": "✨ Invitee",
            "pro": "💎 Pro",
            "free": "🆓 Free",
        }.get(_tier, "🆓 Free")
        st.caption(f"티어: {_tier_emoji}")

    # ── 🧭 STEP 점프 네비게이션 (사용자 요청: 각 단계 독립 실행) ──
    st.markdown("---")
    st.markdown("### 🧭 빠른 이동")
    if st.button("🏠 홈/프로젝트", key="_sb_home", use_container_width=True):
        st.session_state.app_phase = "project_select"
        st.rerun()

    # 활성 프로젝트 있을 때만 STEP 메뉴 노출
    if st.session_state.get("active_project_id"):
        _step_labels = [
            (1, "1️⃣ 소스 선택"),
            (2, "2️⃣ 영상 편집"),
            (3, "3️⃣ AI 대본·자막"),
            (4, "4️⃣ 추적 + 다운로드"),
        ]
        _curr = st.session_state.get("current_step", 1)
        for _n, _label in _step_labels:
            _icon = "▶" if _n == _curr else "  "
            if st.button(f"{_icon} {_label}", key=f"_sb_step_{_n}",
                          use_container_width=True,
                          type="primary" if _n == _curr else "secondary"):
                st.session_state.app_phase = "pipeline"
                st.session_state.current_step = _n
                st.rerun()
    else:
        st.caption("프로젝트를 선택/생성하면 STEP 메뉴가 활성화됩니다.")

    if _sb_uid and whitelist.is_founder(_sb_uid):
        st.markdown("---")
        st.markdown("### 👑 관리자")
        if st.button("📊 관리자 페이지", key="_sb_to_admin", use_container_width=True):
            st.session_state.app_phase = "admin"
            st.rerun()

    # ── 📺 YouTube 자동 업로드 인증 ──
    st.markdown("---")
    st.markdown("### 📺 YouTube 연동")
    _yt_authed = youtube_uploader.is_authenticated()
    if _yt_authed:
        st.success("✅ YouTube 연결됨", icon="🎬")
        if st.button("🚪 로그아웃", key="_yt_logout", use_container_width=True):
            youtube_uploader.revoke_token()
            st.rerun()
    else:
        with st.expander("🔐 YouTube 연결하기"):
            st.caption("Google Cloud Console에서 OAuth Client ID 발급 후 secrets에 추가하세요.")
            if st.button("1. 인증 URL 열기", key="_yt_auth_step1", use_container_width=True):
                _r = youtube_uploader.get_auth_url()
                if _r["ok"]:
                    st.session_state["_yt_auth_url"] = _r["auth_url"]
                else:
                    st.error(_r["error"])
            if st.session_state.get("_yt_auth_url"):
                st.markdown(f"[👉 클릭해서 Google 로그인]({st.session_state['_yt_auth_url']})")
                _yt_code = st.text_input("2. 받은 인증 코드 붙여넣기", key="_yt_code_input")
                if st.button("3. 등록 완료", key="_yt_auth_step3", type="primary",
                              use_container_width=True):
                    _r = youtube_uploader.exchange_code(_yt_code)
                    if _r["ok"]:
                        st.success("✅ 등록 완료!")
                        st.session_state.pop("_yt_auth_url", None)
                        st.rerun()
                    else:
                        st.error(_r["error"])


# ═════════════════════════════════════════════════════════════════
# 라우팅: app_phase → project_select / template_select / pipeline / admin
# ═════════════════════════════════════════════════════════════════
if st.session_state.app_phase == "admin":
    if whitelist.is_founder(st.session_state.get("user_id", "")):
        admin_dashboard.render_admin_page(st)
    else:
        st.error("관리자 페이지는 Founder만 접근할 수 있습니다.")
        st.session_state.app_phase = "project_select"
        st.rerun()
elif st.session_state.app_phase == "project_select":
    render_project_select()
elif st.session_state.app_phase == "template_select":
    render_template_select()
elif st.session_state.app_phase == "pipeline":
    # 활성 프로젝트 없이 STEP 직접 접근 시 — 임시 프로젝트 자동 생성 (UX 개선)
    if not st.session_state.get("active_project_id"):
        st.warning("⚠️ 활성 프로젝트가 없습니다. 임시 프로젝트로 시작합니다.")
        _temp_pid = project_store.create_project(
            f"임시 프로젝트 {time.strftime('%m-%d %H:%M')}",
            product_name="", category="기타",
        )
        st.session_state.active_project_id = _temp_pid
        st.rerun()

    # ── STEP 진행 워크플로우 (AI 영상 SaaS 스타일 큰 카드) ──
    _curr = st.session_state.get("current_step", 1)
    _steps_meta = [
        (1, "🎯", "소스", "제품/주제"),
        (2, "✂️", "편집", "클립 정렬"),
        (3, "🤖", "AI 대본", "viral 패턴"),
        (4, "🔗", "추적+DL", "매출 측정"),
    ]
    _step_html = ('<div style="display:flex;gap:8px;margin:8px 0 24px;'
                  'overflow-x:auto;padding:4px 0;">')
    for _n, _emoji, _label, _sub in _steps_meta:
        if _n == _curr:
            _bg = "linear-gradient(135deg,#FF6B35 0%,#F7931E 100%)"
            _fg = "#fff"
            _border = "transparent"
            _shadow = "0 6px 16px rgba(255,107,53,.35)"
            _opacity = "1"
        elif _n < _curr:
            _bg = "linear-gradient(135deg,#10B981 0%,#059669 100%)"
            _fg = "#fff"
            _border = "transparent"
            _shadow = "0 2px 6px rgba(16,185,129,.2)"
            _opacity = "0.85"
        else:
            _bg = "#F7F8FA"
            _fg = "#9CA3AF"
            _border = "#E5E8EB"
            _shadow = "none"
            _opacity = "1"
        _check = "✓" if _n < _curr else str(_n)
        _step_html += (
            f'<div style="flex:1;min-width:130px;background:{_bg};color:{_fg};'
            f'border:1px solid {_border};border-radius:14px;padding:14px 16px;'
            f'box-shadow:{_shadow};opacity:{_opacity};'
            f'transition:transform .2s ease,box-shadow .2s ease;">'
            f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">'
            f'<div style="width:22px;height:22px;border-radius:50%;'
            f'background:rgba(255,255,255,.25);display:flex;align-items:center;'
            f'justify-content:center;font-size:.7rem;font-weight:700;">{_check}</div>'
            f'<div style="font-size:1.1rem;">{_emoji}</div>'
            f'</div>'
            f'<div style="font-size:.92rem;font-weight:700;line-height:1.2;">{_label}</div>'
            f'<div style="font-size:.72rem;opacity:.75;margin-top:2px;">{_sub}</div>'
            f'</div>'
        )
    _step_html += '</div>'
    st.markdown(_step_html, unsafe_allow_html=True)

    # ── STEP 라우팅 ──
    if _curr == 1:
        render_step1()
    elif _curr == 2:
        render_step2()
    elif _curr == 3:
        render_step3()
    elif _curr == 4:
        render_step4()
