import streamlit as st
import os, json, subprocess, tempfile, time, re, requests, glob as globmod
from pathlib import Path

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

st.set_page_config(page_title="숏폼 자동화 제작기", page_icon="🎬", layout="wide", initial_sidebar_state="expanded")

# ── CSS: Apple/Toss 미니멀 ─────────────────────────────────────────
st.markdown("""
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
:root{--bg:#ffffff;--surface:#f7f8fa;--border:#e5e8eb;--text:#1a1a1a;--muted:#8b95a1;--accent:#1a1a1a;--accent-light:#f2f3f5;--blue:#3182f6;--red:#f04452;--green:#00c471;}
html,body,[class*="css"]{font-family:'Pretendard',sans-serif!important;background:#ffffff!important;color:#1a1a1a!important;}
.stApp{background:#ffffff!important;color:#1a1a1a!important;}
.stApp h1,.stApp h2,.stApp h3,.stApp h4,.stApp h5,.stApp h6{color:#1a1a1a!important;}
.stApp p,.stApp span,.stApp label,.stApp div{color:#1a1a1a!important;}
.stMarkdown,.stMarkdown p,.stMarkdown span{color:#1a1a1a!important;}
[data-testid="stSidebar"]{background:#f7f8fa!important;border-right:1px solid #e5e8eb!important;}
[data-testid="stSidebar"] *{color:#1a1a1a!important;}
[data-testid="stSidebar"] .stSlider span[data-testid="stThumbValue"]{color:#f04452!important;}
.stTextArea textarea,.stTextInput input{background:#f7f8fa!important;border:1px solid #e5e8eb!important;border-radius:12px!important;color:#1a1a1a!important;font-family:'Pretendard',sans-serif!important;}
.stTextArea label,.stTextInput label,.stSelectbox label,.stSlider label,.stRadio label{color:#1a1a1a!important;font-family:'Pretendard',sans-serif!important;}
.stSelectbox>div>div{background:#f7f8fa!important;border:1px solid #e5e8eb!important;border-radius:12px!important;color:#1a1a1a!important;}
.stSelectbox span{color:#1a1a1a!important;}
div[data-testid="stExpander"]{background:#f7f8fa!important;border:1px solid #e5e8eb!important;border-radius:12px!important;}
div[data-testid="stExpander"] *{color:#1a1a1a!important;}
.stButton>button{background:#1a1a1a!important;color:#ffffff!important;border:none!important;border-radius:12px!important;font-family:'Pretendard',sans-serif!important;font-weight:600!important;padding:10px 24px!important;font-size:.9rem!important;transition:all .15s!important;}
.stButton>button:hover{opacity:.85!important;transform:translateY(-1px)!important;box-shadow:0 4px 12px rgba(0,0,0,.15)!important;}
.stButton>button:disabled{background:#e5e8eb!important;color:#8b95a1!important;transform:none!important;box-shadow:none!important;}
.stTabs [data-baseweb="tab-list"]{gap:0;}
.stTabs [data-baseweb="tab"]{font-family:'Pretendard',sans-serif!important;font-weight:600!important;color:#1a1a1a!important;}
.stTabs [aria-selected="false"]{color:#8b95a1!important;}
.stRadio div[role="radiogroup"] label span{color:#1a1a1a!important;}
.card{background:#ffffff;border:1px solid #e5e8eb;border-radius:16px;padding:20px 24px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,.04);}
.card-label{font-size:.75rem;font-weight:600;color:#8b95a1!important;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px;}
.card h3{font-size:1.05rem;font-weight:700;color:#1a1a1a!important;margin:0 0 8px;}
.badge{display:inline-block;font-size:.72rem;font-weight:600;padding:4px 10px;border-radius:20px;}
.badge-dark{background:#1a1a1a;color:#fff!important;}
.badge-blue{background:#e8f3ff;color:#3182f6!important;}
.badge-green{background:#e8faf0;color:#00c471!important;}
.badge-red{background:#fff0f1;color:#f04452!important;}
.badge-gray{background:#f2f3f5;color:#8b95a1!important;}
.info-box{background:#f0f6ff;border:1px solid #d4e4f7;border-radius:12px;padding:12px 16px;font-size:.85rem;color:#1a5dad!important;margin:8px 0;}
.warn-box{background:#fff8e6;border:1px solid #f0d999;border-radius:12px;padding:12px 16px;font-size:.85rem;color:#8a6200!important;margin:8px 0;}
.demo-banner{background:#fff0f1;border:1px solid #fcc;border-radius:12px;padding:12px 16px;font-size:.85rem;color:#c00!important;margin:8px 0;font-weight:600;text-align:center;}
.copy-box{background:#f7f8fa;border:1px solid #e5e8eb;border-radius:12px;padding:14px 18px;font-size:.85rem;color:#1a1a1a!important;margin:8px 0;white-space:pre-wrap;word-break:break-all;}
hr{border-color:#e5e8eb!important;}
</style>
""", unsafe_allow_html=True)

# ── 상태 초기화 ────────────────────────────────────────────────────
defaults = {
    "clips":[], "clip_order":[], "script":"", "output_path":None,
    "tts_done":False, "subtitle_done":False, "sample_subs":[],
    "script_history":[], "subtitle_history":[], "search_results":[],
    "coupang_product":"", "coupang_category":"", "coupang_titles":[],
    "coupang_script":"", "coupang_hashtags":"", "coupang_desc":"",
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── 헬퍼 함수 ─────────────────────────────────────────────────────
def get_api_key(name):
    """Secrets 또는 환경변수에서 API 키 가져오기"""
    try:
        return st.secrets.get(name, "") or os.getenv(name, "")
    except:
        return os.getenv(name, "")

def has_key(name):
    return bool(get_api_key(name))

def call_claude(system_prompt, user_msg, max_tokens=1500):
    api_key = get_api_key("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        import anthropic
        c = anthropic.Anthropic(api_key=api_key)
        m = c.messages.create(
            model="claude-sonnet-4-20250514", max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role":"user","content":user_msg}]
        )
        return m.content[0].text.strip()
    except Exception as e:
        st.error(f"Claude API 오류: {e}")
        return None

def search_pexels(keyword, n=9):
    key = get_api_key("PEXELS_API_KEY")
    if not key:
        return []
    try:
        r = requests.get("https://api.pexels.com/videos/search",
                         headers={"Authorization": key},
                         params={"query": keyword, "per_page": n, "orientation": "portrait"},
                         timeout=10)
        if r.status_code != 200:
            return []
        out = []
        for v in r.json().get("videos", []):
            hd = next((f for f in v["video_files"] if f.get("quality") == "hd"), v["video_files"][0])
            out.append({
                "id": v["id"], "title": f"{keyword} #{v['id']}",
                "thumbnail": v.get("image", ""), "duration": f"0:{v['duration']:02d}",
                "dur_sec": v["duration"], "author": v["user"]["name"],
                "download_url": hd.get("link", ""),
            })
        return out
    except:
        return []

def download_video(url, dest_path):
    """Pexels 영상을 실제 다운로드"""
    try:
        r = requests.get(url, stream=True, timeout=30)
        if r.status_code == 200:
            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
    except:
        pass
    return False

def get_video_duration(path):
    try:
        res = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=10
        )
        return float(json.loads(res.stdout)["format"]["duration"])
    except:
        return 0

def assemble_video(clips, subs, tts_path, target_dur, crop_ratio="9:16"):
    """FFmpeg로 실제 영상 조립 (에러 체크 포함)"""
    tmp = _ensure_dir("shortform_build")

    # 1. 클립 파일 확인
    valid_clips = [c for c in clips if os.path.exists(c["path"])]
    if not valid_clips:
        return None, "클립 파일이 없습니다."

    # 2. concat 파일 생성
    concat_file = tmp / "filelist.txt"
    with open(concat_file, "w") as f:
        for c in valid_clips:
            f.write(f"file '{c['path']}'\n")

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
        return None, f"클립 연결 실패: {r1.stderr[-300:] if r1.stderr else 'unknown error'}"

    # 4. 9:16 크롭 + 자막 오버레이
    vf_filters = []

    # 크롭
    if crop_ratio == "9:16":
        vf_filters.append("scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920")
    else:
        vf_filters.append("scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080")

    # 자막 drawtext (한글 폰트 자동 감지)
    if subs:
        fontpath = find_korean_font()
        if fontpath:
            fontpath_escaped = fontpath.replace("\\", "/").replace(":", "\\:")
            for s in subs:
                text = s["text"].replace("'", "\u2019").replace(":", "\\:").replace(",", "\\,")
                vf_filters.append(
                    f"drawtext=fontfile='{fontpath_escaped}':text='{text}':"
                    f"fontcolor=white:fontsize=48:"
                    f"x=(w-text_w)/2:y=h-200:shadowcolor=black:shadowx=3:shadowy=3:"
                    f"enable='between(t,{s['start']},{s['end']})'"
                )
        else:
            st.warning("한글 폰트를 찾을 수 없어 자막 없이 조립합니다.")

    final_out = tmp / "final.mp4"
    vf_str = ",".join(vf_filters) if vf_filters else "null"

    cmd = ["ffmpeg", "-y", "-i", str(concat_out)]

    # TTS 오디오 합성
    if tts_path and os.path.exists(tts_path):
        cmd += ["-i", tts_path]
        cmd += ["-vf", vf_str, "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-shortest",
                str(final_out)]
    else:
        cmd += ["-vf", vf_str, "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac", str(final_out)]

    r2 = subprocess.run(cmd, capture_output=True, text=True, timeout=180)

    if r2.returncode != 0 or not final_out.exists():
        return None, f"영상 합성 실패: {r2.stderr[-300:] if r2.stderr else 'unknown error'}"

    return str(final_out), None

def extract_coupang_info(url):
    """쿠팡 URL에서 제품명 추출 시도"""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        resp = requests.get(url, headers=headers, timeout=5)
        match = re.search(r'<title>(.*?)</title>', resp.text)
        if match:
            title = match.group(1).replace(" - 쿠팡!", "").replace(" | 쿠팡", "").strip()
            if title and len(title) > 2:
                return {"name": title, "success": True}
    except:
        pass
    return {"name": "", "success": False}

# ── 헤더 ──────────────────────────────────────────────────────────
st.markdown("""
<div style="padding:32px 0 16px;">
  <h1 style="font-size:2rem;font-weight:800;margin:0;">🎬 숏폼 자동화 제작기</h1>
  <p style="color:#8b95a1;font-size:.95rem;margin:4px 0 0;">키워드 검색 → 클립 선택 → AI 스크립트 → TTS → 자막 → 다운로드</p>
</div>
""", unsafe_allow_html=True)

# ── 사이드바 ──────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ 설정")
    st.markdown("---")
    product_name = st.text_input("📦 제품명", placeholder="예: 무선 이어폰 Pro X")
    product_desc = st.text_area("📝 제품 설명", placeholder="특징, 장점 입력", height=85)
    st.markdown("---")

    st.markdown("**🎙️ TTS 설정**")
    tts_engine = st.radio("TTS 엔진", ["🇰🇷 클로바 (한국어)", "🌍 ElevenLabs"], horizontal=True)
    if "클로바" in tts_engine:
        tts_voice = st.selectbox("클로바 음성", [
            "nara - 여성 (자연스러움)", "jinho - 남성 (신뢰감)",
            "nbora - 밝은 여성", "ndain - 차분한 남성",
        ])
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

    st.markdown("---")
    st.markdown("**✂️ 영상 설정**")
    target_dur = st.slider("목표 길이(초)", 15, 60, 30, 5)
    crop_ratio = st.selectbox("화면 비율", ["9:16 세로형 (숏폼)", "1:1 정방형"])

    st.markdown("---")
    with st.expander("🔑 API 연결 상태"):
        for label, env in [
            ("Claude AI", "ANTHROPIC_API_KEY"),
            ("클로바 TTS", "CLOVA_TTS_CLIENT_ID"),
            ("ElevenLabs", "ELEVENLABS_API_KEY"),
            ("Pexels 검색", "PEXELS_API_KEY"),
        ]:
            ok = has_key(env)
            st.markdown(f"{'✅' if ok else '⬜'} **{label}** {'연결됨' if ok else '미연결'}")

# ── 탭 ───────────────────────────────────────────────────────────
tab_coupang, tab_search, tab_clips, tab_script, tab_sub, tab_dl = st.tabs([
    "🛒 쿠팡 파트너스", "🔍 영상 검색", "① 클립 & 순서", "② 스크립트 & TTS", "③ 자막 & 편집", "④ 다운로드"
])

# ═════════════════════════════════════════════════════════════════
# TAB: 쿠팡 파트너스
# ═════════════════════════════════════════════════════════════════
with tab_coupang:
    st.markdown('<div class="card"><div class="card-label">COUPANG PARTNERS</div><h3>🛒 쿠팡 파트너스 숏폼 자동 생성</h3></div>', unsafe_allow_html=True)

    if not has_key("ANTHROPIC_API_KEY"):
        st.markdown('<div class="demo-banner">⚠️ ANTHROPIC_API_KEY 필요 — Secrets에 API 키를 등록하세요</div>', unsafe_allow_html=True)

    # 1. 쿠팡 URL 입력
    st.markdown("#### 1️⃣ 쿠팡 상품 URL 입력")
    coupang_url = st.text_input("쿠팡 상품 링크", placeholder="https://www.coupang.com/vp/products/...", label_visibility="collapsed")

    col_extract, col_status = st.columns([1, 3])
    with col_extract:
        do_extract = st.button("🔍 상품 정보 추출", use_container_width=True)

    if do_extract and coupang_url:
        with st.spinner("상품 정보 추출 중..."):
            info = extract_coupang_info(coupang_url)
            if info["success"]:
                st.session_state.coupang_product = info["name"]
                st.success(f"✅ 추출 완료: {info['name']}")
            else:
                st.warning("자동 추출 실패 — 아래에서 직접 입력해주세요")

    c1, c2 = st.columns(2)
    with c1:
        st.session_state.coupang_product = st.text_input(
            "제품명", value=st.session_state.coupang_product, placeholder="예: 애플 에어팟 프로 2세대"
        )
    with c2:
        st.session_state.coupang_category = st.selectbox(
            "카테고리", ["전자기기", "뷰티/화장품", "패션/의류", "식품", "생활용품", "건강/헬스", "유아/키즈", "기타"]
        )

    if st.session_state.coupang_product:
        pname = st.session_state.coupang_product
        pcat = st.session_state.coupang_category

        st.markdown("---")

        # 2. 후킹 제목 5개
        st.markdown("#### 2️⃣ 후킹 제목 자동 생성")
        if st.button("✨ AI 제목 5개 생성", key="gen_titles"):
            with st.spinner("후킹 제목 생성 중..."):
                result = call_claude(
                    "숏폼 마케팅 전문가. 제목만 출력. 번호 매겨서.",
                    f"제품: {pname}\n카테고리: {pcat}\n\n이 제품의 숏폼 영상 후킹 제목 5개를 만들어줘.\n조건:\n- 클릭 유도형 (궁금증, 충격, 비교)\n- 15자 이내\n- 이모지 1-2개 포함\n- 유튜브 쇼츠/릴스에 최적화"
                )
                if result:
                    st.session_state.coupang_titles = result
                else:
                    st.markdown('<div class="demo-banner">⚠️ API 키 없음 — 데모 모드에서는 생성되지 않습니다</div>', unsafe_allow_html=True)

        if st.session_state.coupang_titles:
            st.code(st.session_state.coupang_titles, language=None)

        st.markdown("---")

        # 3. 스크립트 자동 생성
        st.markdown("#### 3️⃣ 30~45초 스크립트 자동 생성")
        if st.button("✨ AI 스크립트 생성", key="gen_coupang_script"):
            with st.spinner("스크립트 생성 중..."):
                result = call_claude(
                    "쿠팡 파트너스 숏폼 스크립트 전문가. 스크립트만 출력.",
                    f"제품: {pname}\n카테고리: {pcat}\n\n30~45초 분량 숏폼 광고 스크립트를 작성해줘.\n\n필수 구조:\n1. [0-5초] 후킹: 시청자 멈추게 하는 충격적/궁금한 첫 문장\n2. [5-15초] 문제 제시: 일상의 불편함/고민\n3. [15-30초] 제품 소개: 이 제품이 해결해주는 이유\n4. [30-40초] 사용 후기/증거\n5. [40-45초] CTA: '링크 클릭해서 확인해보세요'\n\n조건: 짧은 문장, 구어체, 감정적 표현"
                )
                if result:
                    st.session_state.coupang_script = result
                else:
                    st.markdown('<div class="demo-banner">⚠️ API 키 없음 — 데모 모드에서는 생성되지 않습니다</div>', unsafe_allow_html=True)

        if st.session_state.coupang_script:
            st.session_state.coupang_script = st.text_area(
                "스크립트 (수정 가능)", value=st.session_state.coupang_script, height=180
            )
            # 스크립트를 메인 스크립트에도 반영
            if st.button("📋 이 스크립트를 제작 탭에 적용", key="apply_script"):
                st.session_state.script = st.session_state.coupang_script
                st.success("✅ 스크립트 탭 ②에 적용됨!")

        st.markdown("---")

        # 4. 해시태그 20개
        st.markdown("#### 4️⃣ 해시태그 20개 자동 생성")
        if st.button("✨ 해시태그 20개 생성", key="gen_hashtags"):
            with st.spinner("해시태그 생성 중..."):
                result = call_claude(
                    "SNS 해시태그 전문가. 해시태그만 출력. 줄바꿈 없이 공백으로 구분.",
                    f"제품: {pname}\n카테고리: {pcat}\n\n이 제품 숏폼 영상에 최적화된 해시태그 20개.\n조건:\n- #제품명 #카테고리 필수 포함\n- #쿠팡 #쿠팡추천 #쿠팡파트너스 포함\n- #shorts #fyp #viral 포함\n- 나머지는 검색량 높은 관련 키워드\n- 모두 # 붙여서 공백으로 구분"
                )
                if result:
                    st.session_state.coupang_hashtags = result
                else:
                    st.markdown('<div class="demo-banner">⚠️ API 키 없음 — 데모 모드에서는 생성되지 않습니다</div>', unsafe_allow_html=True)

        if st.session_state.coupang_hashtags:
            st.code(st.session_state.coupang_hashtags, language=None)

        st.markdown("---")

        # 5. 유튜브/인스타 설명란
        st.markdown("#### 5️⃣ 유튜브 / 인스타 설명란 자동 생성")
        if st.button("✨ 설명란 자동 생성", key="gen_desc"):
            with st.spinner("설명란 생성 중..."):
                result = call_claude(
                    "SNS 마케팅 카피라이터. 설명란만 출력.",
                    f"제품: {pname}\n카테고리: {pcat}\n해시태그: {st.session_state.coupang_hashtags}\n\n유튜브 쇼츠 + 인스타 릴스용 설명란을 각각 작성해줘.\n\n[유튜브 설명란]\n- 제품 한줄 소개\n- '쿠팡에서 확인하기 👇' (링크 자리)\n- 해시태그\n\n[인스타 설명란]\n- 감성적 한줄 + 이모지\n- 제품 특징 3줄\n- '프로필 링크에서 확인하세요 🔗'\n- 해시태그"
                )
                if result:
                    st.session_state.coupang_desc = result
                else:
                    st.markdown('<div class="demo-banner">⚠️ API 키 없음 — 데모 모드에서는 생성되지 않습니다</div>', unsafe_allow_html=True)

        if st.session_state.coupang_desc:
            st.code(st.session_state.coupang_desc, language=None)

        st.markdown("---")

        # 6. Pexels 영상 자동 검색 연동
        st.markdown("#### 6️⃣ 관련 영상 자동 검색")
        auto_keywords = pname.split()[0] if pname else ""
        kw_suggestions = [auto_keywords, pcat.split("/")[0], "product showcase", "lifestyle", "close up"]
        kw_suggestions = [k for k in kw_suggestions if k]

        kw_cols = st.columns(len(kw_suggestions))
        for i, kw in enumerate(kw_suggestions):
            with kw_cols[i]:
                if st.button(kw, key=f"ckw_{i}", use_container_width=True):
                    with st.spinner(f"'{kw}' 검색 중..."):
                        st.session_state.search_results = search_pexels(kw, 6)
                    if st.session_state.search_results:
                        st.success(f"✅ {len(st.session_state.search_results)}개 발견 → '영상 검색' 탭에서 확인")
                    elif not has_key("PEXELS_API_KEY"):
                        st.markdown('<div class="demo-banner">⚠️ PEXELS_API_KEY 필요</div>', unsafe_allow_html=True)
                    else:
                        st.info("결과 없음")


# ═════════════════════════════════════════════════════════════════
# TAB: 영상 검색
# ═════════════════════════════════════════════════════════════════
with tab_search:
    st.markdown('<div class="card"><div class="card-label">VIDEO SEARCH</div><h3>🔍 키워드로 무료 영상 검색</h3></div>', unsafe_allow_html=True)

    if not has_key("PEXELS_API_KEY"):
        st.markdown('<div class="demo-banner">⚠️ PEXELS_API_KEY 필요 — Secrets에 등록하세요</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="info-box">Pexels 저작권 무료 영상을 검색하고 바로 클립에 추가할 수 있어요.</div>', unsafe_allow_html=True)

    c1, c2, c3 = st.columns([3, 1, 1])
    with c1:
        kw = st.text_input("키워드 (영어 권장)", placeholder="예: wireless earphones, tech gadget", label_visibility="collapsed", key="kw_input")
    with c2:
        n_results = st.selectbox("개수", [6, 9, 12], index=1, label_visibility="collapsed")
    with c3:
        do_search = st.button("🔍 검색", use_container_width=True)

    if do_search and kw:
        with st.spinner(f"'{kw}' 검색 중..."):
            st.session_state.search_results = search_pexels(kw, n_results)
        if st.session_state.search_results:
            st.success(f"✅ {len(st.session_state.search_results)}개 영상 발견!")
        else:
            st.warning("결과 없음. 다른 키워드를 시도해보세요.")

    if st.session_state.search_results:
        st.markdown("### 검색 결과")
        results = st.session_state.search_results
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
                        if st.button("＋ 클립에 추가", key=f"add_{vid_id}", use_container_width=True):
                            # 실제 다운로드
                            save_dir = _ensure_dir("shortform_clips")
                            dest = save_dir / f"pexels_{vid_id}.mp4"

                            with st.spinner("영상 다운로드 중..."):
                                if v.get("download_url") and download_video(v["download_url"], str(dest)):
                                    dur = get_video_duration(str(dest))
                                    st.session_state.clips.append({
                                        "name": f"pexels_{vid_id}.mp4",
                                        "path": str(dest),
                                        "duration": f"{int(dur//60)}:{int(dur%60):02d}",
                                        "dur_sec": dur,
                                        "search_id": vid_id,
                                        "source": "pexels",
                                    })
                                    st.rerun()
                                else:
                                    st.error("다운로드 실패")


# ═════════════════════════════════════════════════════════════════
# TAB: 클립 & 순서
# ═════════════════════════════════════════════════════════════════
with tab_clips:
    st.markdown('<div class="card"><div class="card-label">STEP 01</div><h3>📁 클립 업로드 & 순서 조정</h3></div>', unsafe_allow_html=True)

    uploaded = st.file_uploader("클립 업로드 (여러 개 가능)", type=["mp4", "mov", "avi"], accept_multiple_files=True, key="clip_uploader")
    if uploaded:
        save_dir = _ensure_dir("shortform_clips")
        new_clips = []
        for f in uploaded:
            dest = save_dir / f.name
            dest.write_bytes(f.read())
            dur = get_video_duration(str(dest))
            dur_str = f"{int(dur//60)}:{int(dur%60):02d}" if dur else "--:--"
            if f.name not in [c["name"] for c in st.session_state.clips]:
                new_clips.append({"name": f.name, "path": str(dest), "duration": dur_str, "dur_sec": dur, "source": "upload"})
        if new_clips:
            st.session_state.clips.extend(new_clips)
            st.success(f"✅ {len(new_clips)}개 추가됨")

    if st.session_state.clips:
        clips = st.session_state.clips
        to_remove = []
        for i, clip in enumerate(clips):
            c1, c2, c3, c4, c5, c6 = st.columns([0.6, 0.4, 0.4, 4, 1.2, 0.7])
            with c1:
                src_badge = "badge-blue" if clip.get("source") == "pexels" else "badge-dark"
                st.markdown(f"<span class='badge {src_badge}'>#{i+1:02d}</span>", unsafe_allow_html=True)
            with c2:
                if i > 0 and st.button("↑", key=f"up_{i}"):
                    clips[i-1], clips[i] = clips[i], clips[i-1]
                    st.rerun()
            with c3:
                if i < len(clips)-1 and st.button("↓", key=f"dn_{i}"):
                    clips[i+1], clips[i] = clips[i], clips[i+1]
                    st.rerun()
            with c4:
                nm = clip["name"][:40] + "..." if len(clip["name"]) > 40 else clip["name"]
                st.markdown(f"<div style='padding-top:6px;'>{nm}</div>", unsafe_allow_html=True)
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

        if st.button("✅ 순서 확정 →"):
            st.session_state.clip_order = [c["path"] for c in clips]
            st.success(f"✅ {len(clips)}개 확정! 탭 ②로 이동하세요.")
    else:
        st.markdown('<div style="text-align:center;padding:40px 0;color:#8b95a1;">📂 영상 검색 탭에서 검색하거나 직접 업로드하세요</div>', unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════════
# TAB: 스크립트 & TTS
# ═════════════════════════════════════════════════════════════════
with tab_script:
    st.markdown('<div class="card"><div class="card-label">STEP 02</div><h3>✍️ AI 스크립트 & 🎙️ TTS 음성</h3></div>', unsafe_allow_html=True)

    if not has_key("ANTHROPIC_API_KEY"):
        st.markdown('<div class="demo-banner">⚠️ ANTHROPIC_API_KEY 미설정 — AI 기능이 작동하지 않습니다</div>', unsafe_allow_html=True)

    pn = product_name or st.session_state.coupang_product
    if not pn:
        st.warning("⚠️ 사이드바에서 제품명을 입력하거나, 쿠팡 파트너스 탭을 먼저 이용하세요.")
    else:
        t1, t2 = st.columns(2)
        with t1:
            tone = st.selectbox("톤", ["🔥 강렬하게", "😊 친근하게", "💎 고급스럽게", "📢 구매유도형"])
        with t2:
            lang = st.selectbox("언어", ["한국어", "영어", "한국어+영어 혼용"])

        if st.button("🤖 AI 스크립트 생성"):
            with st.spinner("생성 중..."):
                result = call_claude(
                    "숏폼 광고 카피라이터. 스크립트만 출력.",
                    f"제품:{pn}\n설명:{product_desc or '없음'}\n톤:{tone}\n언어:{lang}\n길이:{target_dur}초\n조건:첫 문장 강렬, 구매유도, 짧은 문장"
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

    # TTS
    st.markdown("---")
    st.markdown('<div class="card"><div class="card-label">STEP 03</div><h3>🎙️ TTS 음성 생성</h3></div>', unsafe_allow_html=True)

    if st.session_state.script:
        if "클로바" in tts_engine:
            has_tts = has_key("CLOVA_TTS_CLIENT_ID")
        else:
            has_tts = has_key("ELEVENLABS_API_KEY")

        if not has_tts:
            st.markdown(f'<div class="demo-banner">⚠️ {"CLOVA" if "클로바" in tts_engine else "ELEVENLABS"} API 키 미설정 — TTS가 작동하지 않습니다</div>', unsafe_allow_html=True)

        tts_output_path = os.path.join(TMPDIR, "tts_output.mp3")

        if st.button("🎙️ TTS 음성 생성"):
            with st.spinner("음성 생성 중..."):
                tts_success = False

                if "클로바" in tts_engine:
                    clova_id = get_api_key("CLOVA_TTS_CLIENT_ID")
                    clova_sec = get_api_key("CLOVA_TTS_CLIENT_SECRET")
                    speaker = tts_voice.split(" - ")[0].strip()
                    if clova_id and clova_sec:
                        try:
                            resp = requests.post(
                                "https://naveropenapi.apigw.ntruss.com/tts-premium/v1/tts",
                                headers={"X-NCP-APIGW-API-KEY-ID": clova_id, "X-NCP-APIGW-API-KEY": clova_sec, "Content-Type": "application/x-www-form-urlencoded"},
                                data={"speaker": speaker, "text": st.session_state.script, "speed": str(int((tts_speed - 1) * 5)), "format": "mp3"}
                            )
                            if resp.status_code == 200:
                                with open(tts_output_path, "wb") as f:
                                    f.write(resp.content)
                                tts_success = True
                                st.success("✅ 클로바 TTS 완료!")
                            else:
                                st.error(f"클로바 오류: {resp.status_code}")
                        except Exception as e:
                            st.error(f"연결 실패: {e}")
                else:
                    el_key = get_api_key("ELEVENLABS_API_KEY")
                    if el_key and elevenlabs_voice_id:
                        try:
                            resp = requests.post(
                                f"https://api.elevenlabs.io/v1/text-to-speech/{elevenlabs_voice_id}",
                                headers={"xi-api-key": el_key, "Content-Type": "application/json"},
                                json={"text": st.session_state.script, "model_id": "eleven_multilingual_v2",
                                      "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
                                      "speed": tts_speed}
                            )
                            if resp.status_code == 200:
                                with open(tts_output_path, "wb") as f:
                                    f.write(resp.content)
                                tts_success = True
                                st.success("✅ ElevenLabs TTS 완료!")
                            else:
                                st.error(f"ElevenLabs 오류: {resp.status_code}")
                        except Exception as e:
                            st.error(f"연결 실패: {e}")

                # API 키 없으면 데모 모드: 무음 mp3 생성
                if not tts_success and not has_tts:
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
        st.info("스크립트를 먼저 생성해주세요.")


# ═════════════════════════════════════════════════════════════════
# TAB: 자막 & 편집
# ═════════════════════════════════════════════════════════════════
with tab_sub:
    st.markdown('<div class="card"><div class="card-label">STEP 04</div><h3>📝 자막 생성 & 🎬 영상 조립</h3></div>', unsafe_allow_html=True)

    sub_c1, sub_c2 = st.columns(2)
    with sub_c1:
        sub_size = st.slider("자막 크기", 24, 72, 48)
        sub_pos = st.selectbox("위치", ["하단 중앙", "상단 중앙", "중앙"])
    with sub_c2:
        sub_col = st.color_picker("색상", "#FFFFFF")
        sub_bold = st.checkbox("굵게", value=True)

    if st.button("📝 스크립트 기반 자막 생성"):
        if st.session_state.script:
            lines = [l.strip() for l in st.session_state.script.split("\n") if l.strip()]
            subs = []
            t = 0.0
            # 1차: 한국어 기준 글자당 0.25초로 계산
            for l in lines:
                d = max(1.5, len(l) * 0.25)
                subs.append({"start": round(t, 1), "end": round(t + d, 1), "text": l})
                t += d + 0.3

            # 2차: TTS mp3가 있으면 실제 음성 길이에 맞게 비율 조정
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
            st.success("✅ 자막 생성 완료!")
        else:
            st.warning("스크립트를 먼저 생성해주세요.")

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

    # 영상 조립
    st.markdown("---")
    st.markdown('<div class="card"><div class="card-label">STEP 05</div><h3>🎬 최종 영상 조립</h3></div>', unsafe_allow_html=True)

    has_clips = bool(st.session_state.clips)
    if not has_clips:
        st.info("클립을 먼저 추가해주세요 (탭 ①)")
    else:
        st.markdown(f"**{len(st.session_state.clips)}개 클립** · 목표 {target_dur}초 · {'TTS ✅' if st.session_state.tts_done else 'TTS 없음'}")

        if st.button("⚡ 영상 조립 시작", type="primary"):
            prog = st.progress(0)
            stat = st.empty()

            stat.text("📂 클립 확인 중...")
            prog.progress(10)

            # 실제 클립 파일 확인
            valid = [c for c in st.session_state.clips if os.path.exists(c["path"])]
            if not valid:
                st.error("❌ 다운로드된 클립 파일이 없습니다. 영상을 먼저 다운로드해주세요.")
            else:
                stat.text(f"✂️ {len(valid)}개 클립 조립 중...")
                prog.progress(30)

                tts_check = os.path.join(TMPDIR, "tts_output.mp3")
                tts_path = tts_check if st.session_state.tts_done and os.path.exists(tts_check) else None
                subs = st.session_state.sample_subs if st.session_state.subtitle_done else []
                ratio = "9:16" if "9:16" in crop_ratio else "1:1"

                stat.text("🎬 FFmpeg 영상 합성 중... (최대 2분)")
                prog.progress(50)

                output, err_msg = assemble_video(valid, subs, tts_path, target_dur, ratio)

                if output and os.path.exists(output):
                    prog.progress(100)
                    stat.text("✅ 완료!")
                    st.session_state.output_path = output
                    st.success("🎉 영상 조립 완료! 탭 ④에서 다운로드하세요.")
                    st.video(output)
                else:
                    prog.progress(100)
                    st.error(f"❌ 영상 조립 실패: {err_msg or 'FFmpeg 오류'}")


# ═════════════════════════════════════════════════════════════════
# TAB: 다운로드
# ═════════════════════════════════════════════════════════════════
with tab_dl:
    st.markdown('<div class="card"><div class="card-label">STEP 06</div><h3>💾 완성 영상 다운로드</h3></div>', unsafe_allow_html=True)

    pn = product_name or st.session_state.coupang_product or "제품"

    dc1, dc2 = st.columns(2)
    with dc1:
        auto_title = st.text_input("제목", value=f"{pn} 리뷰 | 이거 진짜 괜찮네요 #shorts")
    with dc2:
        auto_tags = st.text_input("해시태그", value=st.session_state.coupang_hashtags or f"#{pn} #숏폼 #리뷰 #shorts #viral #fyp")
    auto_desc = st.text_area("설명", value=st.session_state.coupang_desc or f"{product_desc or ''}\n\n{auto_tags}", height=80)

    st.markdown("### 📥 플랫폼별 다운로드")
    video_ready = st.session_state.get("output_path") and os.path.exists(st.session_state.get("output_path", ""))

    if not video_ready:
        st.markdown('<div class="warn-box">⚠️ 탭 ③에서 영상 조립을 먼저 완료해주세요.</div>', unsafe_allow_html=True)

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
            if video_ready:
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

# (선택) 클로바 TTS
CLOVA_TTS_CLIENT_ID = "..."
CLOVA_TTS_CLIENT_SECRET = "..."
        """, language="toml")
