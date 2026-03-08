import streamlit as st
import os, json, subprocess, tempfile, time, re, requests, glob as globmod, random
from pathlib import Path
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont
import project_store

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


def generate_tts_auto(text, output_path, speaker="nara", voice_id="21m00Tcm4TlvDq8ikWAM", speed=1.0):
    """session_state.tts_engine 기준으로 자동 분기. 성공 시 True."""
    import streamlit as _st
    engine = _st.session_state.get("tts_engine", "elevenlabs")
    if engine == "elevenlabs":
        if generate_tts_elevenlabs(text, output_path, voice_id=voice_id, speed=speed):
            return True
        return generate_tts_clova(text, output_path, speaker=speaker, speed=int((speed - 1) * 5))
    else:
        if generate_tts_clova(text, output_path, speaker=speaker, speed=int((speed - 1) * 5)):
            return True
        return generate_tts_elevenlabs(text, output_path, voice_id=voice_id, speed=speed)


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
/* ── UI/UX 개선: 공통 토큰 ── */
.ux-card{background:#FFFFFF;border:1px solid #E5E7EB;border-radius:12px;padding:24px;margin-bottom:16px;box-shadow:0 2px 8px rgba(0,0,0,0.08);}
.ux-card-title{font-size:.8rem;font-weight:700;color:#FF6B35!important;text-transform:uppercase;letter-spacing:1.2px;margin-bottom:4px;}
.ux-card h4{font-size:1rem;font-weight:700;color:#1A1A2E!important;margin:0 0 12px;}
.ux-sub{color:#6B7280!important;font-size:.82rem;}
/* 사이드바 STEP 강조 */
[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label{border-radius:8px;padding:4px 8px;margin:2px 0;transition:background .15s;}
/* 다음 버튼 (primary) */
button[kind="primary"]{background:#FF6B35!important;color:#fff!important;border:none!important;border-radius:8px!important;font-weight:700!important;}
button[kind="primary"]:hover{background:#E55A2B!important;color:#fff!important;}
/* 이전 버튼 (secondary) */
button[kind="secondary"]{background:#fff!important;color:#1A1A2E!important;border:1px solid #E5E7EB!important;border-radius:8px!important;font-weight:600!important;}
button[kind="secondary"]:hover{background:#F7F8FA!important;color:#1A1A2E!important;}
/* 최적화 카드 */
.opt-card{background:#FFFFFF;border:1px solid #E5E7EB;border-radius:12px;padding:16px 20px;box-shadow:0 2px 8px rgba(0,0,0,0.06);height:100%;}
.opt-card-icon{font-size:1.6rem;margin-bottom:4px;}
.opt-card-title{font-size:.9rem;font-weight:700;color:#1A1A2E!important;margin:4px 0;}
.opt-card-desc{font-size:.78rem;color:#6B7280!important;margin-bottom:8px;}
</style>
""", unsafe_allow_html=True)

# ── 상태 초기화 ────────────────────────────────────────────────────
defaults = {
    "clips":[], "clip_order":[], "script":"", "output_path":None,
    "tts_done":False, "subtitle_done":False, "sample_subs":[],
    "script_history":[], "subtitle_history":[], "search_results":[],
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
    "tts_engine":"elevenlabs",  # "clova" or "elevenlabs"
    # ── 프로젝트 / 템플릿 ──
    "app_phase":"project_select",  # "project_select" | "template_select" | "pipeline"
    "active_project_id":"",
    "active_template":"",
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── 템플릿 정의 ──────────────────────────────────────────────────
TEMPLATES = {
    "coupang_shorts": {
        "name": "🛒 쿠팡 쇼츠",
        "desc": "쿠팡 파트너스 특화. 3초 Hook + 제품 소개 + CTA",
        "hook_type": "problem",
        "cta_position": "하단",
        "retention_booster": True,
        "pattern_interrupt": True,
        "tts_engine": "elevenlabs",
        "content_mode": "구매전환형",
    },
    "shopping_promo": {
        "name": "🏪 쇼핑몰 제품 홍보",
        "desc": "일반 이커머스 제품 홍보용. 혜택 강조 + 구매 유도",
        "hook_type": "benefit",
        "cta_position": "하단",
        "retention_booster": True,
        "pattern_interrupt": False,
        "tts_engine": "elevenlabs",
        "content_mode": "클릭유도형",
    },
    "tiktok_review": {
        "name": "📱 틱톡 리뷰",
        "desc": "솔직 리뷰 스타일. 놀람 Hook + 사용 후기",
        "hook_type": "surprise",
        "cta_position": "하단",
        "retention_booster": True,
        "pattern_interrupt": True,
        "tts_engine": "clova",
        "content_mode": "리뷰형",
    },
    "problem_solving": {
        "name": "🔧 문제 해결 광고",
        "desc": "문제 제시 → 해결 구조. 공감 유도 + 제품 솔루션",
        "hook_type": "problem",
        "cta_position": "하단",
        "retention_booster": True,
        "pattern_interrupt": True,
        "tts_engine": "elevenlabs",
        "content_mode": "문제해결형",
    },
}


# ── 프로젝트 선택 화면 ──────────────────────────────────────────
def render_project_select():
    st.markdown('<div class="ux-card"><div class="ux-card-title">HOME</div><h4>📁 프로젝트 선택</h4><p class="ux-sub">프로젝트를 선택하거나 새로 만들어주세요</p></div>', unsafe_allow_html=True)

    # 새 프로젝트 생성
    with st.expander("➕ 새 프로젝트 만들기", expanded=not bool(project_store.list_projects())):
        _np_name = st.text_input("프로젝트 이름", placeholder="예: 배수구 냄새 제거기", key="_new_prj_name")
        _np_product = st.text_input("제품명 (선택)", placeholder="예: 만능 배수구 클리너", key="_new_prj_product")
        _np_cat = st.selectbox("카테고리", ["전자기기", "뷰티/화장품", "패션/의류", "식품", "생활용품", "건강/헬스", "유아/키즈", "기타"], key="_new_prj_cat")
        if st.button("✅ 프로젝트 생성", key="btn_create_prj", type="primary"):
            if _np_name.strip():
                pid = project_store.create_project(_np_name.strip(), product_name=_np_product, category=_np_cat)
                st.session_state.active_project_id = pid
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
    st.session_state.tts_engine = tpl.get("tts_engine", "elevenlabs")
    st.session_state.cta_position = tpl.get("cta_position", "하단")


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


# ── 카테고리별 해시태그 DB ─────────────────────────────────────────
CATEGORY_HASHTAGS = {
    "생활용품": ["#생활꿀템","#주방용품","#집꾸미기","#살림템","#주부템","#홈리빙","#정리정돈","#생활용품추천","#가성비템","#인테리어소품","#청소꿀팁","#다이소추천","#집콕템","#생활해킹","#편리템","#수납정리"],
    "뷰티/화장품": ["#뷰티템","#스킨케어","#화장품추천","#뷰티하울","#피부관리","#메이크업","#데일리뷰티","#뷰티리뷰","#겟레디윗미","#파데추천","#립스틱추천","#올리브영추천","#뷰티꿀템","#기초화장품","#톤업크림","#선크림추천"],
    "전자기기": ["#전자제품","#가전추천","#스마트홈","#테크템","#갓성비","#IT리뷰","#가젯","#스마트기기","#언박싱","#전자기기추천","#가전제품","#블루투스","#이어폰추천","#충전기추천","#디지털","#테크리뷰"],
    "패션/의류": ["#패션추천","#오오티디","#데일리룩","#코디추천","#패션하울","#쇼핑하울","#옷추천","#스타일링","#패션꿀템","#가성비패션","#트렌드","#봄코디","#여름코디","#가을코디","#겨울코디","#데일리패션"],
    "식품": ["#맛있템","#식품추천","#간식추천","#건강식품","#푸드하울","#먹방","#맛집추천","#다이어트식품","#간편식","#밀키트","#식단관리","#영양제추천","#단백질","#헬시푸드","#제로칼로리","#간식하울"],
    "건강/헬스": ["#건강템","#헬스장","#운동기구","#홈트레이닝","#다이어트","#건강관리","#보충제","#프로틴","#요가","#필라테스","#헬스용품","#건강식품","#비타민","#체중관리","#근력운동","#홈트"],
    "유아/키즈": ["#육아템","#아기용품","#육아필수템","#맘스템","#아이템","#유아용품","#출산준비","#베이비","#키즈템","#아기옷","#이유식","#장난감추천","#육아꿀팁","#초등준비물","#아기간식","#신생아용품"],
    "기타": ["#추천템","#꿀템","#갓성비","#리뷰","#솔직리뷰","#하울","#쇼핑","#언박싱","#쿠팡발견","#트렌드","#인기템","#핫딜","#가성비","#신상품","#필수템","#베스트셀러"],
}
COMMON_HASHTAGS = ["#쿠팡","#쿠팡파트너스","#추천템","#구매링크","#숏폼"]

# ── BGM 카테고리별 검색 키워드 매핑 ─────────────────────────────
BGM_CATEGORY_KEYWORDS = {
    "생활용품": "upbeat positive",
    "뷰티/화장품": "elegant soft",
    "전자기기": "tech modern",
    "패션/의류": "fashion trendy",
    "식품": "cheerful fun",
    "건강/헬스": "energetic motivational",
    "유아/키즈": "cute happy",
    "기타": "upbeat positive",
}

# ── Pexels 카테고리별 추천 검색 키워드 ─────────────────────────
PEXELS_CATEGORY_KEYWORDS = {
    "생활용품": ["product showcase", "home lifestyle", "clean minimal interior"],
    "뷰티/화장품": ["beauty skincare", "cosmetics closeup", "woman self care"],
    "전자기기": ["technology gadget", "unboxing product", "modern device"],
    "패션/의류": ["fashion style outfit", "model walking", "clothing aesthetic"],
    "식품": ["food delicious", "cooking kitchen", "fresh ingredients"],
    "건강/헬스": ["fitness workout", "healthy lifestyle", "gym exercise"],
    "유아/키즈": ["baby cute", "kids playing", "happy children"],
    "기타": ["product review", "minimal background", "lifestyle aesthetic"],
}

# ── CTA 카테고리별 라이브러리 ──────────────────────────────────
CTA_LIBRARY = {
    "생활용품": [
        "지금 바로 쿠팡에서 확인하세요!",
        "링크 타고 최저가 확인 👇",
        "집에 하나쯤 있어야 하는 템!",
        "이거 없으면 손해예요",
        "매일 쓰는 꿀템, 바로가기 👇",
        "정리정돈의 시작, 링크 클릭!",
        "살림 9단의 선택!",
        "가성비 끝판왕 보러가기 →",
        "삶의 질이 달라집니다",
        "지금 할인 중! 서두르세요",
    ],
    "뷰티/화장품": [
        "피부가 달라지는 비밀 👇",
        "쿠팡 최저가 확인하기!",
        "내 피부에 딱 맞는 템 →",
        "데일리 뷰티 필수템!",
        "이 가격에? 바로 확인 👇",
        "겟레디윗미 필수 아이템!",
        "피부 고민 끝! 링크 클릭",
        "뷰티 유튜버 추천템 →",
        "한 번 쓰면 재구매각!",
        "올리브영보다 싸다?! 확인 👇",
    ],
    "전자기기": [
        "스펙 확인하러 가기 →",
        "이 가격 실화? 쿠팡에서 확인!",
        "가성비 끝판왕 보러가기 👇",
        "IT 덕후 추천템!",
        "언박싱 후기가 증명합니다",
        "스마트한 선택, 링크 클릭!",
        "이 기능에 이 가격?! →",
        "테크 템 최저가 확인 👇",
        "놓치면 후회할 가격!",
        "지금 바로 스펙 비교하기",
    ],
    "패션/의류": [
        "코디 완성! 링크 확인 👇",
        "이 옷 어디서 샀냐고 물어봐요",
        "데일리룩 필수템 보러가기 →",
        "이 가격에 이 퀄리티?!",
        "트렌드 선점! 지금 확인 👇",
        "스타일링 꿀템 쿠팡 최저가!",
        "옷잘알이 추천하는 템",
        "코디 고민 끝! 클릭 →",
        "시즌 필수템 보러가기",
        "쿠팡에서 가격 확인 👇",
    ],
    "식품": [
        "이 맛에 이 가격?! 확인 →",
        "자꾸 생각나는 맛 👇",
        "먹어본 사람만 아는 맛!",
        "쿠팡 로켓배송으로 바로 받기!",
        "간식 고민 끝! 링크 클릭",
        "건강하게 맛있게 →",
        "입소문 난 그 제품!",
        "최저가 비교하러 가기 👇",
        "장바구니 필수템!",
        "오늘 주문하면 내일 도착!",
    ],
    "건강/헬스": [
        "건강 투자, 지금 시작 👇",
        "운동 효과 200% 올리는 템!",
        "홈트 필수템 확인하기 →",
        "몸이 달라지는 비밀!",
        "쿠팡 최저가 확인 👇",
        "건강 관리의 첫걸음!",
        "프로틴 가성비 끝판왕 →",
        "운동하는 사람은 다 쓰는 템",
        "다이어트 성공 비결 👇",
        "지금 시작하면 늦지 않아요!",
    ],
    "유아/키즈": [
        "우리 아이 필수템 👇",
        "육아 꿀템 쿠팡 최저가!",
        "엄마들 사이 입소문 난 템 →",
        "아이가 좋아해요! 확인 👇",
        "신생아 맘 필수! 링크 클릭",
        "이 가격에 이 퀄리티?!",
        "육아 고민 끝! 바로가기 →",
        "출산 준비 필수템 확인 👇",
        "아이 간식 추천! 링크 클릭",
        "맘카페에서 난리난 그 제품!",
    ],
    "기타": [
        "지금 바로 확인하세요 👇",
        "쿠팡 최저가 확인하기!",
        "이 가격 놓치면 후회해요 →",
        "링크 타고 바로 확인 👇",
        "가성비 끝판왕!",
        "품절 전에 서두르세요!",
        "솔직 리뷰 보러가기 →",
        "쿠팡에서 바로 구매 가능 👇",
        "인기템 확인하기!",
        "할인 중! 링크 클릭 →",
    ],
}
CTA_COMMON = [
    "쿠팡에서 최저가 확인 👇",
    "링크는 댓글에!",
    "지금 바로 확인하세요!",
    "구매 링크 클릭 →",
    "이 가격 놓치지 마세요!",
    "쿠팡 로켓배송 가능!",
    "할인 중! 서두르세요 👇",
    "좋아요 + 저장 부탁해요!",
    "더 많은 리뷰는 프로필에서!",
    "구독하고 꿀템 받으세요!",
]

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

def search_youtube_shorts(keyword, n=6):
    """YouTube Data API로 관련 숏폼 영상 검색 (참고용)"""
    key = get_api_key("YOUTUBE_API_KEY")
    if not key:
        return []
    try:
        r = requests.get("https://www.googleapis.com/youtube/v3/search",
                         params={"key": key, "q": keyword + " #shorts",
                                 "type": "video", "part": "snippet",
                                 "maxResults": n, "videoDuration": "short",
                                 "order": "viewCount"},
                         timeout=10)
        if r.status_code != 200:
            return []
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
    except:
        return []

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

    # concat hook + body
    concat_file = tmp / "tts_concat.txt"
    with open(concat_file, "w") as f:
        f.write(f"file '{hook_adjusted}'\n")
        if body_tts_path and os.path.exists(body_tts_path):
            f.write(f"file '{body_tts_path}'\n")
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-c:a", "aac", "-b:a", "128k", str(output_path)
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
                           pattern_interrupt=False, retention_booster=False):
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
            pn = st.session_state.get("_w_pname", "") or st.session_state.get("coupang_product", "")
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
            retention_booster=retention_booster
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


def assemble_video(clips, subs, tts_path, target_dur, crop_ratio="9:16", ass_path=None, bgm_path=None, bgm_volume=0.2, cta_text=None, cta_position="하단", cta_duration=3, cta_color="#FFFFFF", pattern_interrupt=False, retention_booster=False):
    """FFmpeg로 실제 영상 조립 (에러 체크 포함, ASS 자막 + BGM 믹싱 지원)"""
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

    if has_tts and has_bgm:
        tts_idx, bgm_idx = 1, 2
        cmd += ["-filter_complex",
                f"[{bgm_idx}:a]volume={bgm_volume}[bgml];[{tts_idx}:a][bgml]amix=inputs=2:duration=first:dropout_transition=2[aout]",
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
                f"[{bgm_idx}:a]volume={bgm_volume}[bgm]",
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
  <h1 style="font-size:2rem;font-weight:800;margin:0;">🎬 숏폼 자동화 제작기</h1>
  <p style="color:#8b95a1;font-size:.95rem;margin:4px 0 0;">소스 선택 → 클립 편집 → 자막+음성 → 다운로드</p>
  <p style="color:#FF6B35;font-size:1.25rem;font-weight:700;margin:12px 0 0;text-align:center;">쿠팡 URL 하나로 → 숏폼 영상 완성 ✨</p>
</div>
""", unsafe_allow_html=True)

# ── 사이드바 ──────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🎬 숏폼 자동화")
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
                                  index=st.session_state.current_step - 1,
                                  key="_nav_step")
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
    nav_prev, _, nav_next = st.columns([1, 3, 1])
    with nav_prev:
        if st.session_state.current_step > 1:
            if st.button("← 이전 단계", key=f"prev_{st.session_state.current_step}", type="secondary"):
                st.session_state.current_step -= 1
                st.rerun()
    with nav_next:
        if st.session_state.current_step < 4:
            if st.button("다음 단계 →", key=f"next_{st.session_state.current_step}", type="primary"):
                st.session_state.current_step += 1
                st.rerun()


# ═════════════════════════════════════════════════════════════════
# render_step1: 🔍 소스 선택
# ═════════════════════════════════════════════════════════════════
def render_step1():
    st.markdown('<div class="ux-card"><div class="ux-card-title">STEP 01</div><h4>소스 선택</h4><p class="ux-sub">영상 소스를 선택하고, 필요 시 제품 정보를 입력하세요</p></div>', unsafe_allow_html=True)

    # ── 영상 소스 (메인) ──
    st.markdown("#### 🎬 영상 소스")
    _src_opts = ["🛒 쿠팡 URL", "🖼️ 이미지 업로드", "🎥 영상 직접 업로드"]
    _src_map = {"🛒 쿠팡 URL": "URL", "🖼️ 이미지 업로드": "이미지", "🎥 영상 직접 업로드": "영상"}
    _src_reverse = {"URL": "🛒 쿠팡 URL", "이미지": "🖼️ 이미지 업로드", "영상": "🎥 영상 직접 업로드"}
    _cur_src_label = _src_reverse.get(st.session_state.source_type, "🛒 쿠팡 URL")
    _src_sel = st.radio("소스 유형 선택", _src_opts, horizontal=True, key="source_type_radio",
                        index=_src_opts.index(_cur_src_label) if _cur_src_label in _src_opts else 0)
    st.session_state.source_type = _src_map[_src_sel]

    # ── 제품 정보 + 쿠팡 링크 (접힌 상태) ──
    _exp_label = "📦 제품 기본 정보 & 쿠팡 링크"
    if st.session_state.get("coupang_product"):
        _exp_label += f"  —  ✅ {st.session_state.coupang_product}"
    with st.expander(_exp_label, expanded=False):
        s1c1, s1c2 = st.columns(2)
        with s1c1:
            product_name = st.text_input("📦 제품명", placeholder="예: 무선 이어폰 Pro X", key="_w_pname")
        with s1c2:
            product_desc = st.text_area("📝 제품 설명", placeholder="특징, 장점 입력", height=85, key="_w_pdesc")

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

    # ═══════ A) 쿠팡 URL ═══════
    if st.session_state.source_type == "URL":
        st.markdown("#### 🛒 쿠팡 상품 URL")
        if not has_key("ANTHROPIC_API_KEY"):
            st.markdown('<div class="demo-banner">⚠️ ANTHROPIC_API_KEY 필요 — Secrets에 API 키를 등록하세요</div>', unsafe_allow_html=True)

        coupang_url = st.text_input("쿠팡 상품 URL", placeholder="https://www.coupang.com/vp/products/...", label_visibility="collapsed")

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

        st.markdown("---")

        # ─── 제품 이미지 자동 추출 ───
        st.markdown("### 🛒 제품 이미지 자동 추출")
        st.markdown('<div class="info-box">상품 URL에서 제품 이미지를 자동 추출하고, Ken Burns 효과로 영상화합니다.</div>', unsafe_allow_html=True)

        if coupang_url:
            if st.button("📸 이미지 추출하기", key="extract_imgs_coupang"):
                with st.spinner("제품 이미지 추출 중..."):
                    imgs = extract_product_images(coupang_url)
                    if imgs:
                        st.session_state.product_images = imgs
                        st.success(f"✅ {len(imgs)}개 이미지 추출 완료!")
                    else:
                        st.warning("이미지 추출 실패 — 쿠팡의 봇 차단 정책 때문일 수 있어요. 아래에서 직접 업로드하세요.")
        else:
            st.info("위에서 상품 URL을 입력하면 이미지를 자동 추출할 수 있어요.")

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
                with st.spinner("이미지 다운로드 + Ken Burns 효과 적용 중... (시간이 걸릴 수 있어요)"):
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

        # ── ① Pexels 자동 검색 ──
        if st.session_state.coupang_product and not st.session_state.pexels_searched and has_key("PEXELS_API_KEY"):
            keyword = st.session_state.coupang_product
            results = search_pexels(keyword)
            if results:
                st.session_state.pexels_results = results
            st.session_state.pexels_searched = True

        # ── ② YouTube 추천 링크 (API 키 유무 무관) ──
        if st.session_state.coupang_product:
            st.markdown("### 📺 YouTube 참고 숏폼")
            _yt_kw = st.session_state.coupang_product
            if has_key("YOUTUBE_API_KEY"):
                _yt_pname = st.session_state.get("_w_pname", "") or st.session_state.coupang_product or ""
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
                # API 키 없으면 검색 링크만
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

        # ── ③ 인스타그램 추천 링크 ──
        if st.session_state.coupang_product:
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

        # ── ④ 타오바오 제조사 영상 안내 ──
        st.info("💡 이 제품을 타오바오에서 검색해서 제조사 홍보 영상을 다운받으세요.\n다운받은 영상은 C) 영상 직접 업로드에 올리세요.")
        with st.expander("📥 타오바오 영상 다운로드 방법"):
            st.markdown("""
1. 타오바오에서 제품명으로 검색
2. 상세페이지에서 제조사 홍보 영상 확인
3. 크롬 확장프로그램(Video Downloader)으로 저장
4. 여러 판매처에서 다양한 영상 확보
5. 다운받은 영상은 **C) 영상 직접 업로드**에 올리세요
            """)
        st.markdown("---")

        # ─── Pexels 배경 영상 ───
        st.markdown("### 🎬 Pexels 배경 영상 (인트로/아웃트로용)")

        if not has_key("PEXELS_API_KEY"):
            st.markdown('<div class="demo-banner">⚠️ PEXELS_API_KEY 필요 — Secrets에 등록하세요</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="info-box">카테고리 기반 추천 영상을 자동 검색하거나, 직접 키워드로 검색하세요.</div>', unsafe_allow_html=True)

        # ── 카테고리 기반 추천 영상 자동 검색 ──
        _rec_cat = st.session_state.coupang_category or "기타"
        _rec_keywords = PEXELS_CATEGORY_KEYWORDS.get(_rec_cat, PEXELS_CATEGORY_KEYWORDS["기타"])

        st.markdown(f"**🤖 `{_rec_cat}` 카테고리 추천 키워드:**")
        rec_cols = st.columns(len(_rec_keywords) + 1)
        _auto_kw = None
        for ri, rkw in enumerate(_rec_keywords):
            with rec_cols[ri]:
                if st.button(f"🔍 {rkw}", key=f"rec_kw_{ri}", use_container_width=True):
                    _auto_kw = rkw
        with rec_cols[-1]:
            if st.button("⚡ 전체 추천", key="rec_all", use_container_width=True):
                _auto_kw = " ".join(_rec_keywords[:2])

        if _auto_kw:
            with st.spinner(f"'{_auto_kw}' 추천 영상 검색 중..."):
                st.session_state.pexels_results = search_pexels(_auto_kw, 9)
            if st.session_state.pexels_results:
                st.success(f"✅ '{_auto_kw}' — {len(st.session_state.pexels_results)}개 추천 영상 발견!")
            else:
                st.warning("추천 결과 없음. 아래에서 직접 키워드를 입력해보세요.")

        st.markdown("---")
        st.caption("또는 직접 키워드 검색:")
        c1, c2, c3 = st.columns([3, 1, 1])
        with c1:
            kw = st.text_input("키워드 (영어 권장)", placeholder="예: product showcase, minimal background", label_visibility="collapsed", key="kw_input")
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

        # ─── 🛒 제품 동영상 자동 추출 ───
        st.markdown("### 🛒 제품 동영상 자동 추출")
        st.markdown('<div class="info-box">쿠팡 상품 페이지에서 제품 소개 동영상을 자동 추출합니다.</div>', unsafe_allow_html=True)

        if coupang_url:
            if st.button("🎥 제품 동영상 추출", key="extract_prod_videos", use_container_width=True):
                with st.spinner("제품 동영상 URL 추출 중..."):
                    prod_videos = extract_product_videos(coupang_url)
                    if prod_videos:
                        st.session_state["_prod_videos"] = prod_videos
                        st.success(f"✅ {len(prod_videos)}개 제품 동영상 발견!")
                    else:
                        st.warning("동영상을 찾지 못했어요. 쿠팡은 봇 차단이 심해 이미지 추출 또는 직접 업로드를 이용하세요.")

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
        else:
            st.info("위에서 상품 URL을 입력하면 제품 동영상을 자동 추출할 수 있어요.")

        st.markdown("---")

        # ─── 🤖 AI 트렌드 키워드 추천 ───
        st.markdown("### 🤖 AI 트렌드 키워드 추천")
        st.markdown('<div class="info-box">AI가 제품과 관련된 트렌드 숏폼 키워드와 영상 포맷을 추천합니다.</div>', unsafe_allow_html=True)

        if not has_key("ANTHROPIC_API_KEY"):
            st.markdown('<div class="demo-banner">⚠️ ANTHROPIC_API_KEY 필요</div>', unsafe_allow_html=True)
        else:
            _ai_pname = st.session_state.get("_w_pname", "") or st.session_state.coupang_product or ""
            _ai_cat = st.session_state.coupang_category or "기타"

            if st.button("✨ AI 키워드 추천 받기", key="ai_trend_btn", use_container_width=True, disabled=(not _ai_pname)):
                with st.spinner("AI가 트렌드 키워드를 분석 중..."):
                    trend_result = call_claude(
                        "숏폼 트렌드 전문가. 핵심만 간결하게 출력.",
                        f"제품: {_ai_pname}\n카테고리: {_ai_cat}\n\n"
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

            if not _ai_pname:
                st.caption("💡 위에서 제품명을 입력하면 AI 추천을 받을 수 있어요.")

    # ═══════ B) 이미지 업로드 ═══════
    elif st.session_state.source_type == "이미지":
        st.markdown("### 🖼️ 이미지 직접 업로드")
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
            kb_dur_b = st.slider("이미지당 시간 (초)", 2, 4, 3, key="kb_dur_b")

            if st.button("🎬 Ken Burns 영상 생성", key="kb_gen_b", use_container_width=True):
                with st.spinner("Ken Burns 효과 적용 중..."):
                    out_path, err = images_to_kenburns_video(local_paths, kb_dur_b)
                    if out_path:
                        dur = get_video_duration(out_path)
                        st.session_state.clips.append({
                            "name": f"업로드이미지_kenburns.mp4",
                            "path": out_path,
                            "duration": f"{int(dur//60)}:{int(dur%60):02d}",
                            "dur_sec": dur,
                            "source": "kenburns",
                        })
                        st.success(f"✅ Ken Burns 영상 생성 완료! ({dur:.0f}초) → STEP 2 클립에 자동 추가됨")
                        st.video(out_path)
                    else:
                        st.error(f"❌ 영상 생성 실패: {err}")

    # ═══════ C) 영상 직접 업로드 ═══════
    elif st.session_state.source_type == "영상":
        st.markdown("### 🎥 영상 직접 업로드")
        st.markdown('<div class="info-box">내 영상 파일을 직접 업로드해 클립에 추가합니다. (mp4, mov, avi, webm 지원)</div>', unsafe_allow_html=True)
        st.info("💡 타오바오/알리 등에서 확보한 제품 홍보 영상을 여기에 업로드하세요.")

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

        # 타오바오 안내
        st.markdown("---")
        st.info("💡 이 제품을 타오바오에서 검색해서 제조사 홍보 영상을 다운받으세요.")
        with st.expander("📥 타오바오 영상 다운로드 방법"):
            st.markdown("""
1. 타오바오에서 제품명으로 검색
2. 상세페이지에서 제조사 홍보 영상 확인
3. 크롬 확장프로그램(Video Downloader)으로 저장
4. 여러 판매처에서 다양한 영상 확보
5. 다운받은 영상을 위에서 업로드하세요
            """)

    _render_nav_buttons()


# ═════════════════════════════════════════════════════════════════
# render_step2: 🎬 클립 편집
# ═════════════════════════════════════════════════════════════════
def render_step2():
    target_dur = st.session_state.get("_w_target_dur", 30)

    st.markdown('<div class="ux-card"><div class="ux-card-title">STEP 02</div><h4>클립 편집</h4><p class="ux-sub">순서 조정 & 용도 태그</p></div>', unsafe_allow_html=True)

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
                    st.rerun()
            with c3:
                if i < len(clips)-1 and st.button("↓", key=f"dn_{i}"):
                    clips[i+1], clips[i] = clips[i], clips[i+1]
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

    _render_nav_buttons()


# ═════════════════════════════════════════════════════════════════
# render_step3: 🎙️ 자막 + 음성
# ═════════════════════════════════════════════════════════════════
def render_step3():
    target_dur = st.session_state.get("_w_target_dur", 30)
    crop_ratio = st.session_state.get("_w_crop_ratio", "9:16 세로형 (숏폼)")

    st.markdown('<div class="ux-card"><div class="ux-card-title">STEP 03</div><h4>영상 생성</h4><p class="ux-sub">제목 · 스크립트 · TTS · 자막 · BGM · 조립</p></div>', unsafe_allow_html=True)

    if not has_key("ANTHROPIC_API_KEY"):
        st.markdown('<div class="demo-banner">⚠️ ANTHROPIC_API_KEY 미설정 — AI 기능이 작동하지 않습니다</div>', unsafe_allow_html=True)

    # ═══════ 🎯 조회수 최적화 패널 ═══════
    st.markdown('<div class="ux-card"><div class="ux-card-title">OPTIMIZE</div><h4>🎯 조회수 최적화</h4><p class="ux-sub">조회수와 완시율을 높이기 위한 자동 최적화 옵션입니다. 영상 조립 시 자동 적용됩니다.</p></div>', unsafe_allow_html=True)

    opt_c1, opt_c2, opt_c3 = st.columns(3)
    with opt_c1:
        st.markdown('<div class="opt-card">', unsafe_allow_html=True)
        st.markdown("**🎯 Hook A/B 테스트**")
        st.caption("첫 3초만 다른 영상 2~3개 자동 생성")
        st.session_state.hook_test_enabled = st.checkbox(
            "Hook A/B 활성화",
            value=st.session_state.hook_test_enabled,
            help="같은 제품으로 첫 3초만 다른 영상 2~3개를 자동 생성합니다.",
            key="opt_hook_test",
            label_visibility="collapsed"
        )
        if st.session_state.hook_test_enabled:
            if not st.session_state.clips:
                st.markdown('<span class="badge badge-dark">⚠️ 클립 필요</span>', unsafe_allow_html=True)
                st.caption("STEP 1에서 클립을 먼저 추가하세요")
            else:
                st.session_state.hook_version_count = st.radio(
                    "버전 수", [2, 3], horizontal=True, key="opt_hook_count",
                    index=0 if st.session_state.hook_version_count == 2 else 1
                )
                st.caption("A: 문제 제시 / B: 놀람 / C: 손해 회피")
        st.markdown('</div>', unsafe_allow_html=True)
    with opt_c2:
        st.markdown('<div class="opt-card">', unsafe_allow_html=True)
        st.markdown("**⚡ Pattern Interrupt**")
        st.caption("중간에 시각 변화를 자동 삽입")
        st.session_state.pattern_interrupt_enabled = st.checkbox(
            "Pattern Interrupt 활성화",
            value=st.session_state.pattern_interrupt_enabled,
            help="영상 중간에 zoom, jump cut, 키워드 강조 등 시각 변화를 자동 삽입합니다.",
            key="opt_pattern_interrupt",
            label_visibility="collapsed"
        )
        if st.session_state.pattern_interrupt_enabled:
            st.caption("10%: zoom / 25%: cut / 40%: 강조 / 60%: flash")
        st.markdown('</div>', unsafe_allow_html=True)
    with opt_c3:
        st.markdown('<div class="opt-card">', unsafe_allow_html=True)
        st.markdown("**📈 Retention Booster**")
        st.caption("완시율 극대화 자동 최적화")
        st.session_state.retention_booster_enabled = st.checkbox(
            "Retention Booster 활성화",
            value=st.session_state.retention_booster_enabled,
            help="완시율 최적화: 첫 5초 자막 밀도 증가, 2초 시각 변화, Benefit 강조, CTA 타이밍 최적화",
            key="opt_retention_booster",
            label_visibility="collapsed"
        )
        if st.session_state.retention_booster_enabled:
            st.caption("자막 밀도 + 시각 변화 + Benefit 강조 + CTA 최적화")
        st.markdown('</div>', unsafe_allow_html=True)
    st.markdown("---")

    # ── AI 제목 9개 생성 (쿠팡 전용) ──
    if st.session_state.coupang_product:
        pname = st.session_state.coupang_product
        pcat = st.session_state.coupang_category

        st.markdown("#### 1️⃣ AI 제목 자동 생성 (9개)")
        st.markdown('<div class="info-box">3가지 유형 × 3개씩 = 총 9개 제목을 AI가 생성합니다. 📌 버튼으로 원하는 제목을 바로 적용하세요.</div>', unsafe_allow_html=True)

        if st.button("✨ AI 제목 9개 생성", key="gen_titles"):
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
                    f"제품: {pname}\n카테고리: {pcat}\n콘텐츠 목적: {cmode}\n{mode_emphasis.get(cmode, '')}\n\n아래 3가지 유형별로 각 3개씩 총 9개의 숏폼 제목을 만들어줘.\n\n[궁금증유발]\n- '이거 모르면 손해', '진짜 이게 돼?' 같은 호기심 자극 스타일\n[문제해결]\n- '이것 때문에 고민 끝', '해결한 제품' 같은 솔루션 제시 스타일\n[혜택강조]\n- '이 가격에?', '가성비 끝판왕' 같은 가격/혜택 강조 스타일\n\n조건:\n- 각 제목 15자 이내\n- 이모지 1개 포함\n- 유형 라벨 없이, 3줄 빈 줄로 유형 구분\n- 총 9줄 출력 (유형당 3줄)"
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
        st.markdown("#### 📋 쿠팡 30~45초 스크립트 자동 생성")
        if st.button("✨ AI 스크립트 생성", key="gen_coupang_script"):
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
                result = call_claude(
                    "쿠팡 파트너스 숏폼 스크립트 전문가. 스크립트만 출력.",
                    f"제품: {pname}\n카테고리: {pcat}\n콘텐츠 목적: {cmode}\n스타일 가이드: {mode_guide.get(cmode, '')}\n\n30~45초 분량 숏폼 광고 스크립트를 작성해줘.\n\n필수 구조:\n1. [0-5초] 후킹: 시청자 멈추게 하는 충격적/궁금한 첫 문장\n2. [5-15초] 문제 제시: 일상의 불편함/고민\n3. [15-30초] 제품 소개: 이 제품이 해결해주는 이유\n4. [30-40초] 사용 후기/증거\n5. [40-45초] CTA: '링크 클릭해서 확인해보세요'\n\n조건: '{cmode}' 목적에 맞게, 짧은 문장, 구어체, 감정적 표현"
                )
                if result:
                    st.session_state.coupang_script = result
                else:
                    st.markdown('<div class="demo-banner">⚠️ API 키 없음 — 데모 모드에서는 생성되지 않습니다</div>', unsafe_allow_html=True)

        if st.session_state.coupang_script:
            st.session_state.coupang_script = st.text_area(
                "스크립트 (수정 가능)", value=st.session_state.coupang_script, height=180
            )
            if st.button("📋 이 스크립트를 메인 스크립트에 적용", key="apply_script"):
                st.session_state.script = st.session_state.coupang_script
                st.success("✅ 메인 스크립트에 적용됨!")

        st.markdown("---")

    # ── 후킹 문구 + 메인 스크립트 ──
    pn = st.session_state.get("_w_pname", "") or st.session_state.coupang_product
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
        if st.button("🪝 후킹 문구 5개 생성", key="gen_hooks"):
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
    _engine_opts = ["🌍 ElevenLabs (자연스럽고 감정 풍부)", "🇰🇷 네이버 클로바 (안정적, 한국어 특화)"]
    _engine_map = {"🌍 ElevenLabs (자연스럽고 감정 풍부)": "elevenlabs", "🇰🇷 네이버 클로바 (안정적, 한국어 특화)": "clova"}
    _engine_reverse = {"elevenlabs": _engine_opts[0], "clova": _engine_opts[1]}
    _default_engine = st.session_state.tts_engine
    if not _has_el and _has_clova:
        _default_engine = "clova"
    elif _has_el:
        _default_engine = "elevenlabs"
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
        if st.session_state.tts_engine == "clova":
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
            pn_for_highlight = st.session_state.get("_w_pname", "") or st.session_state.coupang_product or ""
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
            _pname = st.session_state.get("_w_pname", "") or st.session_state.coupang_product or "제품"
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
                    stat.text(f"🪝 Hook A/B 테스트: {len(st.session_state.hook_versions)}개 버전 생성 중...")
                    prog.progress(30)

                    try:
                        hook_results = assemble_hook_versions(
                            valid, subs, tts_path, target_dur, crop_ratio=ratio,
                            ass_path=ass_file, bgm_path=bgm_file, bgm_volume=bgm_vol,
                            cta_text=cta_t, cta_position=cta_p, cta_duration=cta_d, cta_color=cta_clr,
                            hook_clip_path=None, hooks=st.session_state.hook_versions, hook_dur=3.0,
                            pattern_interrupt=_pi_on, retention_booster=_rb_on
                        )
                    except subprocess.TimeoutExpired:
                        st.error("⏱️ Hook 영상 생성 시간 초과 — 클립 수를 줄이거나 목표 길이를 짧게 설정해주세요.")
                        hook_results = []
                    except Exception as e:
                        st.error(f"❌ Hook 영상 생성 중 오류: {e}")
                        hook_results = []

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
                                                      retention_booster=_rb_on)

                    if output and os.path.exists(output):
                        prog.progress(100)
                        stat.text("✅ 완료!")
                        st.session_state.output_path = output
                        st.success("🎉 영상 조립 완료! STEP 4에서 다운로드하세요.")
                        st.video(output)
                    else:
                        prog.progress(100)
                        st.error(f"❌ 영상 조립 실패: {err_msg or 'FFmpeg 오류'}")

    _render_nav_buttons()


# ═════════════════════════════════════════════════════════════════
# render_step4: ⬇️ 미리보기 + 다운로드
# ═════════════════════════════════════════════════════════════════
def render_step4():
    st.markdown('<div class="ux-card"><div class="ux-card-title">STEP 04</div><h4>다운로드</h4><p class="ux-sub">해시태그 · 설명란 · 썸네일 · 다운로드</p></div>', unsafe_allow_html=True)

    if not has_key("ANTHROPIC_API_KEY"):
        st.markdown('<div class="demo-banner">⚠️ ANTHROPIC_API_KEY 미설정 — AI 기능이 작동하지 않습니다</div>', unsafe_allow_html=True)

    # ── 해시태그 20개 ──
    if st.session_state.coupang_product:
        pname = st.session_state.coupang_product
        pcat = st.session_state.coupang_category

        st.markdown("#### 1️⃣ 해시태그 자동 생성 (AI + DB)")
        st.markdown('<div class="info-box">AI 맞춤 10개 + 카테고리 DB 5개 + 공통 필수 5개 = 총 20개 해시태그를 생성합니다.</div>', unsafe_allow_html=True)

        if st.button("✨ 해시태그 20개 생성", key="gen_hashtags"):
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
        if st.button("✨ 설명란 자동 생성", key="gen_desc"):
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

    # ── 썸네일 자동 생성 ──
    st.markdown("#### 3️⃣ 썸네일 반자동 생성")
    st.markdown('<div class="card"><div class="card-label">THUMBNAIL</div><h3>🖼️ 썸네일 반자동 생성</h3></div>', unsafe_allow_html=True)
    st.markdown('<div class="info-box">3가지 템플릿 + 2가지 해상도로 썸네일을 자동 생성합니다. 제품 이미지가 있으면 자동으로 활용됩니다.</div>', unsafe_allow_html=True)

    pn = st.session_state.get("_w_pname", "") or st.session_state.coupang_product or "제품"

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

    pn = st.session_state.get("_w_pname", "") or st.session_state.coupang_product or "제품"
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

    # ═══════ Hook A/B 테스트 결과 미리보기 ═══════
    _hook_versions = st.session_state.get("hook_versions", [])
    _hook_has_videos = any(h.get("video_path") and os.path.exists(h.get("video_path", "")) for h in _hook_versions)

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

    # ═══════ 플랫폼별 다운로드 (기존 단일 영상) ═══════
    st.markdown("### 📥 플랫폼별 다운로드")
    video_ready = st.session_state.get("output_path") and os.path.exists(st.session_state.get("output_path", ""))

    if not video_ready:
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
# 라우팅: app_phase → project_select / template_select / pipeline
# ═════════════════════════════════════════════════════════════════
if st.session_state.app_phase == "project_select":
    render_project_select()
elif st.session_state.app_phase == "template_select":
    render_template_select()
elif st.session_state.app_phase == "pipeline":
    if st.session_state.current_step == 1:
        render_step1()
    elif st.session_state.current_step == 2:
        render_step2()
    elif st.session_state.current_step == 3:
        render_step3()
    elif st.session_state.current_step == 4:
        render_step4()
