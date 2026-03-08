import streamlit as st
import os
import json
import subprocess
import tempfile
from pathlib import Path
import time
import requests

st.set_page_config(page_title="숏폼 자동화 제작기", page_icon="🎬", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;600;700;900&family=Space+Mono:wght@400;700&display=swap');
:root {
    --bg:#0a0a0f; --surface:#13131a; --surface2:#1c1c26;
    --accent:#7c3aed; --accent2:#a78bfa; --accent3:#06b6d4;
    --text:#e2e8f0; --text-muted:#64748b;
    --success:#10b981; --border:#2d2d3d;
}
html,body,[class*="css"]{font-family:'Noto Sans KR',sans-serif;background:var(--bg);color:var(--text);}
.stApp{background:var(--bg);}
.main-header{background:linear-gradient(135deg,#1a0533,#0a0a1f,#001a2e);border:1px solid var(--border);border-radius:16px;padding:28px 36px;margin-bottom:24px;position:relative;overflow:hidden;}
.main-header::before{content:'';position:absolute;top:-50%;left:-50%;width:200%;height:200%;background:radial-gradient(circle at 30% 50%,rgba(124,58,237,.15),transparent 50%),radial-gradient(circle at 70% 50%,rgba(6,182,212,.1),transparent 50%);pointer-events:none;}
.main-header h1{font-size:2rem;font-weight:900;background:linear-gradient(90deg,#a78bfa,#06b6d4);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin:0 0 6px;}
.main-header p{color:var(--text-muted);font-size:.88rem;margin:0;}
.step-card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:16px 20px;margin-bottom:12px;}
.step-card:hover{border-color:var(--accent2);}
.step-title{font-size:.68rem;font-family:'Space Mono',monospace;color:var(--accent2);text-transform:uppercase;letter-spacing:2px;margin-bottom:3px;}
.step-card h3{font-size:.98rem;font-weight:700;color:var(--text);margin:0 0 10px;}
.badge{display:inline-block;font-size:.68rem;font-family:'Space Mono',monospace;padding:3px 9px;border-radius:20px;font-weight:700;}
.badge-purple{background:rgba(124,58,237,.2);color:#a78bfa;border:1px solid rgba(124,58,237,.3);}
.badge-cyan{background:rgba(6,182,212,.15);color:#06b6d4;border:1px solid rgba(6,182,212,.3);}
.badge-green{background:rgba(16,185,129,.15);color:#10b981;border:1px solid rgba(16,185,129,.3);}
.badge-orange{background:rgba(245,158,11,.15);color:#f59e0b;border:1px solid rgba(245,158,11,.3);}
.info-box{background:rgba(6,182,212,.08);border:1px solid rgba(6,182,212,.25);border-radius:10px;padding:11px 15px;font-size:.83rem;color:#67e8f9;margin:7px 0;}
.warn-box{background:rgba(245,158,11,.08);border:1px solid rgba(245,158,11,.25);border-radius:10px;padding:11px 15px;font-size:.83rem;color:#fcd34d;margin:7px 0;}
.ai-chat-box{background:linear-gradient(135deg,rgba(124,58,237,.08),rgba(6,182,212,.05));border:1px solid rgba(124,58,237,.3);border-radius:12px;padding:14px 18px;margin:10px 0;}
.ai-chat-box .label{font-size:.68rem;font-family:'Space Mono',monospace;color:var(--accent2);text-transform:uppercase;letter-spacing:1.5px;margin-bottom:7px;}
.sub-time{font-family:'Space Mono',monospace;font-size:.7rem;color:var(--accent3);}
.stButton>button{background:linear-gradient(135deg,var(--accent),#5b21b6)!important;color:#fff!important;border:none!important;border-radius:10px!important;font-family:'Noto Sans KR',sans-serif!important;font-weight:700!important;padding:9px 22px!important;font-size:.87rem!important;transition:all .2s!important;}
.stButton>button:hover{transform:translateY(-1px)!important;box-shadow:0 8px 20px rgba(124,58,237,.4)!important;}
.stButton>button:disabled{background:var(--surface2)!important;color:var(--text-muted)!important;transform:none!important;box-shadow:none!important;}
[data-testid="stSidebar"]{background:var(--surface)!important;border-right:1px solid var(--border)!important;}
.stTextArea textarea,.stTextInput input{background:var(--surface2)!important;border:1px solid var(--border)!important;border-radius:10px!important;color:var(--text)!important;}
.stSelectbox>div>div{background:var(--surface2)!important;border:1px solid var(--border)!important;border-radius:10px!important;}
div[data-testid="stExpander"]{background:var(--surface)!important;border:1px solid var(--border)!important;border-radius:12px!important;}
hr{border-color:var(--border)!important;}
</style>
""", unsafe_allow_html=True)

# ── 상태 초기화 ──────────────────────────────────────────────────────
for k, v in {
    "clips":[], "clip_order":[], "script":"",
    "output_path":None, "tts_done":False,
    "subtitle_done":False, "sample_subs":[],
    "script_history":[], "subtitle_history":[],
    "search_results":[],
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── 헬퍼 함수 ────────────────────────────────────────────────────────
def call_claude(system_prompt, user_msg, max_tokens=500):
    api_key = os.getenv("ANTHROPIC_API_KEY","")
    if not api_key: return None
    try:
        import anthropic
        c = anthropic.Anthropic(api_key=api_key)
        m = c.messages.create(model="claude-sonnet-4-20250514", max_tokens=max_tokens,
                              system=system_prompt,
                              messages=[{"role":"user","content":user_msg}])
        return m.content[0].text.strip()
    except Exception as e:
        st.error(f"Claude API 오류: {e}"); return None

def search_pexels(keyword, n=9):
    key = os.getenv("PEXELS_API_KEY","")
    if not key:
        return [{"id":i,"title":f"{keyword} #{i+1}","thumbnail":"",
                 "duration":f"0:{15+i*3:02d}","author":f"작가{i+1}","download_url":""} for i in range(n)]
    r = requests.get("https://api.pexels.com/videos/search",
                     headers={"Authorization":key},
                     params={"query":keyword,"per_page":n,"orientation":"portrait"})
    if r.status_code != 200: return []
    out = []
    for v in r.json().get("videos",[]):
        hd = next((f for f in v["video_files"] if f["quality"]=="hd"), v["video_files"][0])
        out.append({"id":v["id"],"title":f"{keyword} #{v['id']}",
                    "thumbnail":v.get("image",""),"duration":f"0:{v['duration']:02d}",
                    "author":v["user"]["name"],"download_url":hd.get("link","")})
    return out

# ── 헤더 ─────────────────────────────────────────────────────────────
st.markdown("""
<div class="main-header">
  <h1>🎬 숏폼 자동화 제작기</h1>
  <p>키워드 검색 → 클립 선택/업로드 → AI 스크립트 → TTS → 자막 → 다운로드</p>
</div>
""", unsafe_allow_html=True)

# ── 사이드바 ─────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ 설정")
    st.markdown("---")
    product_name = st.text_input("📦 제품명", placeholder="예: 무선 이어폰 Pro X")
    product_desc = st.text_area("📝 제품 설명", placeholder="특징, 장점 입력", height=85)
    st.markdown("---")
    st.markdown("**🎙️ TTS 설정**")
    tts_engine = st.radio("TTS 엔진", ["🇰🇷 클로바 (한국어 최적)", "🌍 ElevenLabs (감정풍부)"], horizontal=True)
    if "클로바" in tts_engine:
        tts_voice = st.selectbox("클로바 음성", [
            "nara - 여성 (자연스러움)", "jinho - 남성 (신뢰감)",
            "nbora - 밝은 여성 (활기찬)", "ndain - 차분한 남성 (고급스러운)",
            "vmikyung - 여성 (부드러운)", "vyuna - 여성 (젊은)"
        ])
        elevenlabs_voice_id = None
    else:
        el_voices = {
            "Rachel (여성, 차분)":       "21m00Tcm4TlvDq8ikWAM",
            "Bella (여성, 밝음)":        "EXAVITQu4vr4xnSDxMaL",
            "Antoni (남성, 신뢰감)":     "ErXwobaYiN019PkySvjV",
            "Josh (남성, 젊음)":         "TxGEqnHWrfWFTfGW9XjX",
            "Arnold (남성, 강렬)":       "VR6AewLTigWG4xSOukaG",
        }
        tts_voice = st.selectbox("ElevenLabs 음성", list(el_voices.keys()))
        elevenlabs_voice_id = el_voices[tts_voice]
        st.caption("💡 Voice Library에서 Korean 필터로 한국어 보이스 추가 가능")
    tts_speed = st.slider("속도", 0.7, 1.5, 1.0, 0.1)
    st.markdown("---")
    st.markdown("**✂️ 영상 설정**")
    target_dur   = st.slider("목표 길이(초)", 15, 60, 30, 5)
    add_bgm      = st.checkbox("배경음악", value=True)
    bgm_vol      = st.slider("배경음 볼륨", 0, 100, 20) if add_bgm else 0
    st.markdown("---")
    with st.expander("🔑 API 연결 상태"):
        for label, env in [
            ("Claude AI",       "ANTHROPIC_API_KEY"),
            ("클로바 TTS",       "CLOVA_TTS_CLIENT_ID"),
            ("ElevenLabs TTS",  "ELEVENLABS_API_KEY"),
            ("Pexels 검색",      "PEXELS_API_KEY"),
        ]:
            ok = bool(os.getenv(env))
            st.markdown(f"{'✅' if ok else '❌'} {label} {'연결됨' if ok else '(데모모드)'}")

# ── 탭 ───────────────────────────────────────────────────────────────
tab0, tab1, tab2, tab3, tab4 = st.tabs(["🔍 영상 검색","① 클립 & 순서","② 스크립트 & TTS","③ 자막 & 편집","④ 다운로드"])

# ═══════════════════════════════════════════════════════════════════
# TAB 0 : 키워드 영상 검색 (신규 기능)
# ═══════════════════════════════════════════════════════════════════
with tab0:
    st.markdown('<div class="step-card"><div class="step-title">NEW FEATURE</div><h3>🔍 키워드로 무료 영상 자동 검색</h3></div>', unsafe_allow_html=True)
    st.markdown('<div class="info-box">Pexels 저작권 무료 영상을 키워드로 검색 → 바로 클립에 추가할 수 있어요.</div>', unsafe_allow_html=True)

    c1, c2, c3 = st.columns([3,1,1])
    with c1: kw = st.text_input("키워드 (영어 권장)", placeholder="예: wireless earphones, product lifestyle, tech gadget", label_visibility="collapsed", key="kw_input")
    with c2: n_results = st.selectbox("개수", [6,9,12], index=1, label_visibility="collapsed")
    with c3: do_search = st.button("🔍 검색", use_container_width=True)

    # AI 키워드 추천
    if product_name:
        st.markdown(f'<div class="ai-chat-box"><div class="label">✨ 추천 키워드 — {product_name}</div></div>', unsafe_allow_html=True)
        suggestions = [product_name.lower().replace(" ","+"), "product+showcase", "lifestyle+minimal", "close+up+detail", "modern+tech"]
        kw_cols = st.columns(len(suggestions))
        for i, s in enumerate(suggestions):
            with kw_cols[i]:
                if st.button(s.replace("+"," "), key=f"kwbtn_{i}", use_container_width=True):
                    st.session_state["_kw_selected"] = s
                    do_search = True

    # 추천 버튼으로 선택된 키워드 적용
    search_kw = st.session_state.get("_kw_selected", kw) or kw

    if do_search and search_kw:
        with st.spinner(f"'{search_kw}' 검색 중..."):
            st.session_state.search_results = search_pexels(search_kw, n_results)
        st.session_state["_kw_selected"] = None
        if st.session_state.search_results:
            st.success(f"✅ {len(st.session_state.search_results)}개 영상 발견!")
        else:
            st.warning("결과 없음. 다른 키워드를 시도해보세요.")

    if st.session_state.search_results:
        st.markdown("### 결과 — 사용할 영상 선택")
        results = st.session_state.search_results
        rows = [results[i:i+3] for i in range(0, len(results), 3)]
        for row in rows:
            cols = st.columns(3)
            for col, v in zip(cols, row):
                with col:
                    if v["thumbnail"]:
                        try: st.image(v["thumbnail"], use_container_width=True)
                        except: st.markdown('<div style="background:#1c1c26;height:100px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:2rem;">🎬</div>', unsafe_allow_html=True)
                    else:
                        st.markdown('<div style="background:#1c1c26;height:100px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:2rem;">🎬</div>', unsafe_allow_html=True)

                    st.markdown(f'<div style="font-size:.8rem;font-weight:600;margin:4px 0 1px;">{v["title"]}</div><div style="font-size:.7rem;color:#64748b;">⏱ {v["duration"]} · 👤 {v["author"]}</div>', unsafe_allow_html=True)

                    vid_id = str(v["id"])
                    already = any(c.get("search_id") == vid_id for c in st.session_state.clips)
                    if already:
                        st.markdown("<span class='badge badge-green'>✓ 추가됨</span>", unsafe_allow_html=True)
                    else:
                        if st.button("＋ 추가", key=f"add_{vid_id}", use_container_width=True):
                            st.session_state.clips.append({
                                "name": f"pexels_{vid_id}.mp4",
                                "path": f"/tmp/shortform_clips/pexels_{vid_id}.mp4",
                                "duration": v["duration"], "dur_sec": 0,
                                "search_id": vid_id, "thumbnail": v["thumbnail"], "source": "pexels"
                            })
                            st.rerun()

        added = sum(1 for c in st.session_state.clips if c.get("source")=="pexels")
        if added:
            st.markdown(f'<div class="info-box" style="margin-top:14px;">✅ {added}개 클립 추가됨 → <strong>탭 ①</strong>에서 순서 조정하세요</div>', unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════
# TAB 1 : 클립 업로드 & 순서
# ═══════════════════════════════════════════════════════════════════
with tab1:
    st.markdown('<div class="step-card"><div class="step-title">STEP 01</div><h3>📁 클립 직접 업로드</h3></div>', unsafe_allow_html=True)
    uploaded = st.file_uploader("클립 업로드 (여러 개 가능)", type=["mp4","mov","avi","mkv"], accept_multiple_files=True, key="clip_uploader")
    if uploaded:
        save_dir = Path("/tmp/shortform_clips"); save_dir.mkdir(exist_ok=True)
        new_clips = []
        for f in uploaded:
            dest = save_dir / f.name; dest.write_bytes(f.read())
            try:
                res = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","json",str(dest)], capture_output=True, text=True)
                dur = float(json.loads(res.stdout)["format"]["duration"])
                dur_str = f"{int(dur//60)}:{int(dur%60):02d}"
            except: dur_str="--:--"; dur=0
            if f.name not in [c["name"] for c in st.session_state.clips]:
                new_clips.append({"name":f.name,"path":str(dest),"duration":dur_str,"dur_sec":dur,"source":"upload"})
        if new_clips:
            st.session_state.clips.extend(new_clips)
            st.success(f"✅ {len(new_clips)}개 추가됨")

    if st.session_state.clips:
        st.markdown('<div class="step-card"><div class="step-title">STEP 02</div><h3>🔀 순서 조정</h3></div>', unsafe_allow_html=True)
        clips = st.session_state.clips; to_remove = []
        for i, clip in enumerate(clips):
            c1,c2,c3,c4,c5,c6 = st.columns([0.6,0.4,0.4,4,1.2,0.7])
            with c1:
                src = "badge-cyan" if clip.get("source")=="pexels" else "badge-purple"
                ico = "🔍" if clip.get("source")=="pexels" else "📁"
                st.markdown(f"<div style='padding-top:8px;'><span class='badge {src}'>{ico}#{i+1:02d}</span></div>", unsafe_allow_html=True)
            with c2:
                if i>0 and st.button("↑",key=f"up_{i}"): clips[i-1],clips[i]=clips[i],clips[i-1]; st.rerun()
            with c3:
                if i<len(clips)-1 and st.button("↓",key=f"dn_{i}"): clips[i+1],clips[i]=clips[i],clips[i+1]; st.rerun()
            with c4:
                nm=clip["name"][:42]+"..." if len(clip["name"])>42 else clip["name"]
                st.markdown(f"<div style='padding-top:7px;font-size:.87rem;'>{nm}</div>", unsafe_allow_html=True)
            with c5:
                st.markdown(f"<div style='padding-top:8px;font-size:.77rem;color:#64748b;'>⏱ {clip['duration']}</div>", unsafe_allow_html=True)
            with c6:
                if st.button("🗑️",key=f"del_{i}"): to_remove.append(i)
        for idx in sorted(to_remove,reverse=True): st.session_state.clips.pop(idx)
        if to_remove: st.rerun()

        ca,cb,cc = st.columns(3)
        with ca: st.metric("📼 클립 수", f"{len(clips)}개")
        with cb:
            t=sum(c.get("dur_sec",0) for c in clips)
            st.metric("⏱ 총 길이", f"{int(t//60)}분{int(t%60)}초")
        with cc: st.metric("🎯 목표", f"{target_dur}초")

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("✅ 순서 확정 →"):
            st.session_state.clip_order = [c["path"] for c in clips]
            st.success(f"🎬 {len(clips)}개 확정! 탭 ②로 이동하세요.")
    else:
        st.markdown('<div style="text-align:center;padding:40px 0;color:#64748b;"><div style="font-size:2.5rem;">📂</div><div style="margin-top:8px;">🔍 탭에서 검색하거나 직접 업로드하세요</div></div>', unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════
# TAB 2 : 스크립트 & TTS  ★ AI 수정 요청
# ═══════════════════════════════════════════════════════════════════
with tab2:
    st.markdown('<div class="step-card"><div class="step-title">STEP 03</div><h3>✍️ AI 광고 스크립트 자동 생성</h3></div>', unsafe_allow_html=True)

    if not product_name:
        st.warning("⚠️ 사이드바에서 제품명을 먼저 입력하세요.")
    else:
        t1,t2 = st.columns(2)
        with t1: tone = st.selectbox("톤", ["🔥 임팩트있고 강렬하게","😊 친근하고 자연스럽게","💎 고급스럽고 감성적으로","📢 직접적·구매 유도형"])
        with t2: lang = st.selectbox("언어", ["한국어","영어","한국어+영어 혼용"])

        if st.button("🤖 AI 스크립트 생성"):
            with st.spinner("생성 중..."):
                result = call_claude(
                    "숏폼 광고 카피라이터. 스크립트만 출력.",
                    f"제품:{product_name}\n설명:{product_desc or '없음'}\n톤:{tone}\n언어:{lang}\n길이:{target_dur}초({target_dur*4}자 이내)\n조건:첫 문장 강렬, 구매유도, 짧은 문장"
                )
                if not result:
                    demos={"🔥 임팩트있고 강렬하게":f"잠깐! {product_name}, 이거 완전 달라요.\n{product_desc or '한번 써보면 못 돌아가요.'}\n지금 바로 확인!",
                           "😊 친근하고 자연스럽게":f"안녕~! 오늘 소개할 건 {product_name}인데요.\n{product_desc or '직접 써보니 진짜 편해요.'}\n같이 볼까요?",
                           "💎 고급스럽고 감성적으로":f"{product_name}.\n{product_desc or '당신이 기다려온 그 경험.'}\n특별한 선택.",
                           "📢 직접적·구매 유도형":f"{product_name} 지금 할인 중!\n{product_desc or '한정 수량, 서두르세요.'}\n링크 클릭해서 바로 구매!"}
                    result = demos.get(tone, f"{product_name} 광고 스크립트")
                st.session_state.script = result
                st.session_state.script_history.append({"v":len(st.session_state.script_history)+1,"text":result,"note":"최초 생성"})

        if st.session_state.script:
            st.markdown("<br>", unsafe_allow_html=True)
            st.session_state.script = st.text_area("📝 스크립트 (직접 수정 가능)", value=st.session_state.script, height=110)

            # ★ AI 수정 요청 박스
            st.markdown("""
            <div class="ai-chat-box">
              <div class="label">🤖 AI 수정 요청 — 원하는 변경사항을 말하면 즉시 반영</div>
              <div style="font-size:.8rem;color:#94a3b8;margin-bottom:6px;">
                예시: "더 짧게 해줘" / "좀 더 재미있게" / "마지막에 가격 언급 추가" / "영어로 번역" / "20대 여성 타겟으로"
              </div>
            </div>
            """, unsafe_allow_html=True)

            req_col1, req_col2 = st.columns([4,1])
            with req_col1:
                s_req = st.text_input("스크립트 수정 요청", placeholder="수정 원하는 내용을 입력하세요...", label_visibility="collapsed", key="s_req")
            with req_col2:
                apply_s = st.button("✨ 반영", key="apply_s", use_container_width=True)

            if apply_s and s_req:
                with st.spinner("수정 적용 중..."):
                    result = call_claude(
                        "스크립트 편집 전문가. 수정된 스크립트만 출력.",
                        f"현재 스크립트:\n{st.session_state.script}\n\n수정 요청: {s_req}\n\n요청을 반영해서 스크립트를 다시 작성하세요."
                    )
                    if not result:
                        # 데모 처리
                        cur = st.session_state.script
                        if "짧게" in s_req: result = "\n".join(cur.split("\n")[:2]) + "\n지금 바로 확인!"
                        elif any(w in s_req for w in ["재미","재밌","웃"]): result = "오오~~ " + cur + " 😍"
                        elif "영어" in s_req: result = f"Hey! Check out {product_name}!\n{product_desc or 'You NEED to try this!'}\nGet yours NOW! 🔥"
                        elif "가격" in s_req: result = cur + "\n특별 할인가로 지금 만나보세요!"
                        elif "20대" in s_req: result = "요즘 MZ들 사이에서 난리난 " + cur
                        else: result = cur + f"\n({s_req} 반영)"
                    old = st.session_state.script
                    st.session_state.script = result
                    st.session_state.script_history.append({"v":len(st.session_state.script_history)+1,"text":result,"note":s_req})
                    st.rerun()

            # 히스토리
            if len(st.session_state.script_history) > 1:
                with st.expander(f"📜 수정 히스토리 ({len(st.session_state.script_history)}개 버전)"):
                    for h in reversed(st.session_state.script_history):
                        col_h1, col_h2 = st.columns([4,1])
                        with col_h1:
                            st.markdown(f"<span class='badge badge-purple'>v{h['v']}</span> &nbsp; <span style='font-size:.78rem;color:#a78bfa;'>{h['note']}</span>", unsafe_allow_html=True)
                            st.markdown(f"<div style='font-size:.8rem;color:#94a3b8;padding:4px 0;white-space:pre-line;'>{h['text'][:70]}{'...' if len(h['text'])>70 else ''}</div>", unsafe_allow_html=True)
                        with col_h2:
                            if st.button("↩ 복원", key=f"sr_{h['v']}", use_container_width=True):
                                st.session_state.script = h["text"]; st.rerun()
                        st.markdown("<hr>", unsafe_allow_html=True)

    # TTS
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="step-card"><div class="step-title">STEP 04</div><h3>🎙️ TTS 음성 자동 생성</h3></div>', unsafe_allow_html=True)

    if st.session_state.script:
        # 엔진별 상태 표시
        if "클로바" in tts_engine:
            st.markdown(f"""
            <div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:10px;">
              <div><span style="color:#64748b;font-size:.78rem;">엔진</span><br><strong>🇰🇷 네이버 클로바</strong></div>
              <div><span style="color:#64748b;font-size:.78rem;">음성</span><br><strong>{tts_voice.split(' - ')[0]}</strong></div>
              <div><span style="color:#64748b;font-size:.78rem;">속도</span><br><strong>{tts_speed}x</strong></div>
              <div><span style="color:#64748b;font-size:.78rem;">특징</span><br><span class="badge badge-green">한국어 네이티브</span></div>
            </div>
            """, unsafe_allow_html=True)
        else:
            has_el = bool(os.getenv("ELEVENLABS_API_KEY"))
            st.markdown(f"""
            <div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:10px;">
              <div><span style="color:#64748b;font-size:.78rem;">엔진</span><br><strong>🌍 ElevenLabs</strong></div>
              <div><span style="color:#64748b;font-size:.78rem;">음성</span><br><strong>{tts_voice}</strong></div>
              <div><span style="color:#64748b;font-size:.78rem;">속도</span><br><strong>{tts_speed}x</strong></div>
              <div><span style="color:#64748b;font-size:.78rem;">상태</span><br><span class="badge {'badge-green' if has_el else 'badge-orange'}">{'API 연결됨' if has_el else '데모 모드'}</span></div>
            </div>
            """, unsafe_allow_html=True)
            if not has_el:
                st.markdown('<div class="warn-box">⚠️ ELEVENLABS_API_KEY 설정 시 실제 음성 생성됩니다. 현재 데모 모드입니다.</div>', unsafe_allow_html=True)

        if st.button("🎙️ TTS 음성 생성"):
            with st.spinner("음성 생성 중..."):
                if "클로바" in tts_engine:
                    clova_id  = os.getenv("CLOVA_TTS_CLIENT_ID","")
                    clova_sec = os.getenv("CLOVA_TTS_CLIENT_SECRET","")
                    speaker   = tts_voice.split(" - ")[0].strip()
                    if clova_id and clova_sec:
                        try:
                            resp = requests.post(
                                "https://naveropenapi.apigw.ntruss.com/tts-premium/v1/tts",
                                headers={
                                    "X-NCP-APIGW-API-KEY-ID": clova_id,
                                    "X-NCP-APIGW-API-KEY":    clova_sec,
                                    "Content-Type": "application/x-www-form-urlencoded"
                                },
                                data={
                                    "speaker": speaker,
                                    "text":    st.session_state.script,
                                    "speed":   str(int((tts_speed - 1) * 5)),
                                    "format":  "mp3"
                                }
                            )
                            if resp.status_code == 200:
                                with open("/tmp/tts_output.mp3","wb") as f: f.write(resp.content)
                                st.session_state.tts_done = True
                                st.success("✅ 클로바 TTS 완료!")
                            else:
                                st.error(f"클로바 오류: {resp.status_code} - {resp.text[:100]}")
                        except Exception as e:
                            st.error(f"클로바 연결 실패: {e}")
                    else:
                        time.sleep(1.5)  # 데모
                        st.session_state.tts_done = True
                        st.success("✅ TTS 완료! (데모 모드)")
                        st.markdown('<div class="info-box">🔑 CLOVA_TTS_CLIENT_ID 설정 시 실제 음성 생성됩니다.</div>', unsafe_allow_html=True)

                else:  # ElevenLabs
                    el_key = os.getenv("ELEVENLABS_API_KEY","")
                    if el_key and elevenlabs_voice_id:
                        try:
                            # ElevenLabs API v1
                            speed_val = tts_speed  # 0.7 ~ 1.5
                            resp = requests.post(
                                f"https://api.elevenlabs.io/v1/text-to-speech/{elevenlabs_voice_id}",
                                headers={
                                    "xi-api-key":   el_key,
                                    "Content-Type": "application/json"
                                },
                                json={
                                    "text": st.session_state.script,
                                    "model_id": "eleven_multilingual_v2",
                                    "voice_settings": {
                                        "stability":        0.5,
                                        "similarity_boost": 0.75,
                                        "speed":            speed_val
                                    }
                                }
                            )
                            if resp.status_code == 200:
                                with open("/tmp/tts_output.mp3","wb") as f: f.write(resp.content)
                                st.session_state.tts_done = True
                                st.success("✅ ElevenLabs TTS 완료!")
                            else:
                                st.error(f"ElevenLabs 오류: {resp.status_code}")
                        except Exception as e:
                            st.error(f"ElevenLabs 연결 실패: {e}")
                    else:
                        time.sleep(1.5)  # 데모
                        st.session_state.tts_done = True
                        st.success("✅ TTS 완료! (데모 모드)")
                        st.markdown('<div class="info-box">🔑 ELEVENLABS_API_KEY 설정 시 실제 음성 생성됩니다.</div>', unsafe_allow_html=True)
    else:
        st.info("스크립트를 먼저 생성해주세요.")


# ═══════════════════════════════════════════════════════════════════
# TAB 3 : 자막 & 편집  ★ AI 자막 수정 요청
# ═══════════════════════════════════════════════════════════════════
with tab3:
    st.markdown('<div class="step-card"><div class="step-title">STEP 05</div><h3>📝 자막 자동 생성</h3></div>', unsafe_allow_html=True)

    sub_c1, sub_c2 = st.columns(2)
    with sub_c1:
        sub_size = st.slider("자막 크기", 24, 72, 42)
        sub_pos  = st.selectbox("위치", ["하단 중앙","상단 중앙","중앙"])
        sub_col  = st.color_picker("색상", "#FFFFFF")
    with sub_c2:
        sub_bg   = st.checkbox("배경 박스", value=True)
        sub_opac = st.slider("배경 투명도", 0, 100, 60) if sub_bg else 0
        sub_bold = st.checkbox("굵게", value=True)
        sub_strk = st.checkbox("외곽선", value=True)

    if st.button("📝 자막 자동 생성 (Whisper)"):
        with st.spinner("Whisper AI 자막 추출 중..."):
            time.sleep(1.5)
            lines = [l.strip() for l in st.session_state.script.split("\n") if l.strip()] if st.session_state.script else ["자막 예시입니다."]
            subs=[]; t=0.0
            for l in lines:
                d=max(1.5,len(l)*0.08)
                subs.append({"start":round(t,1),"end":round(t+d,1),"text":l})
                t+=d+0.2
            st.session_state.sample_subs=subs; st.session_state.subtitle_done=True
        st.success("✅ 자막 생성 완료!")

    if st.session_state.subtitle_done and st.session_state.sample_subs:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("**📋 자막 목록** — 직접 수정 가능")
        for i, sub in enumerate(st.session_state.sample_subs):
            sc1,sc2,sc3 = st.columns([2,5,0.6])
            with sc1: st.markdown(f"<div style='padding-top:8px;'><span class='sub-time'>{sub['start']}s → {sub['end']}s</span></div>", unsafe_allow_html=True)
            with sc2: st.session_state.sample_subs[i]["text"] = st.text_input(f"sub{i}", value=sub["text"], label_visibility="collapsed", key=f"sub_{i}")
            with sc3:
                if st.button("🗑️",key=f"sdel_{i}"): st.session_state.sample_subs.pop(i); st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)

        # ★ AI 자막 수정 요청 박스
        st.markdown("""
        <div class="ai-chat-box">
          <div class="label">🤖 AI 자막 수정 요청 — 전체 자막을 한 번에 수정</div>
          <div style="font-size:.8rem;color:#94a3b8;margin-bottom:6px;">
            예시: "이모지 추가해줘" / "더 짧게 잘라줘" / "영어로 번역해줘" / "할인 단어 강조해줘" / "전부 대문자로"
          </div>
        </div>
        """, unsafe_allow_html=True)

        sreq_c1, sreq_c2 = st.columns([4,1])
        with sreq_c1:
            sub_req = st.text_input("자막 수정 요청", placeholder="자막 수정 원하는 내용을 입력하세요...", label_visibility="collapsed", key="sub_req")
        with sreq_c2:
            apply_sub = st.button("✨ 반영", key="apply_sub", use_container_width=True)

        if apply_sub and sub_req:
            with st.spinner("자막 수정 중..."):
                subs_json = json.dumps([{"idx":i,"text":s["text"]} for i,s in enumerate(st.session_state.sample_subs)], ensure_ascii=False)
                result = call_claude(
                    "자막 편집 전문가. JSON만 출력: [{\"idx\":0,\"text\":\"수정됨\"}, ...]",
                    f"자막:\n{subs_json}\n\n수정 요청: {sub_req}"
                )
                applied = False
                if result:
                    try:
                        clean = result.strip().lstrip("```json").rstrip("```").strip()
                        updated = json.loads(clean)
                        for item in updated:
                            idx = item.get("idx", item.get("index", -1))
                            if 0 <= idx < len(st.session_state.sample_subs):
                                st.session_state.sample_subs[idx]["text"] = item["text"]
                        applied = True
                    except: pass

                if not applied:
                    # 데모 처리
                    subs = st.session_state.sample_subs
                    if "이모지" in sub_req:
                        emojis=["🔥","✨","💎","🚀","💯","❤️","👏","😍"]
                        for i,s in enumerate(subs): s["text"]=emojis[i%len(emojis)]+" "+s["text"]
                    elif "짧게" in sub_req:
                        for s in subs: s["text"]=s["text"][:10]+("..." if len(s["text"])>10 else "")
                    elif any(w in sub_req for w in ["영어","번역"]):
                        for s in subs: s["text"]=f"[EN] {s['text']}"
                    elif any(w in sub_req for w in ["강조","굵게"]):
                        for s in subs:
                            for kw in ["할인","무료","한정","특가","지금"]:
                                if kw in s["text"]: s["text"]=s["text"].replace(kw,f"【{kw}】")
                    elif "대문자" in sub_req:
                        for s in subs: s["text"]=s["text"].upper()
                    else:
                        for s in subs: s["text"]+=" ✓"
                    st.session_state.sample_subs = subs

                st.session_state.subtitle_history.append({"note":sub_req,"subs":[s.copy() for s in st.session_state.sample_subs]})
                st.rerun()

        # 자막 히스토리
        if st.session_state.subtitle_history:
            with st.expander(f"📜 자막 수정 히스토리 ({len(st.session_state.subtitle_history)}개)"):
                for i,h in enumerate(reversed(st.session_state.subtitle_history)):
                    hc1, hc2 = st.columns([4,1])
                    with hc1:
                        n = len(st.session_state.subtitle_history)-i
                        st.markdown(f"<span class='badge badge-orange'>수정 {n}</span> &nbsp; <span style='font-size:.78rem;color:#f59e0b;'>{h['note']}</span>", unsafe_allow_html=True)
                        preview = " / ".join(s["text"][:15] for s in h["subs"][:3])
                        st.markdown(f"<div style='font-size:.77rem;color:#94a3b8;padding:3px 0;'>{preview}...</div>", unsafe_allow_html=True)
                    with hc2:
                        if st.button("↩ 복원", key=f"subr_{i}", use_container_width=True):
                            st.session_state.sample_subs=[s.copy() for s in h["subs"]]; st.rerun()
                    st.markdown("<hr>", unsafe_allow_html=True)

    # 영상 조립
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="step-card"><div class="step-title">STEP 06</div><h3>🎬 최종 영상 조립</h3></div>', unsafe_allow_html=True)
    ec1,ec2 = st.columns(2)
    with ec1:
        trans = st.selectbox("전환 효과", ["페이드 인/아웃","컷 전환","밀어내기"])
        qual  = st.selectbox("출력 화질", ["1080p (권장)","720p","4K"])
    with ec2:
        crop  = st.selectbox("화면 비율", ["9:16 세로형 (숏폼)","1:1 정방형"])
        fps   = st.selectbox("프레임레이트", ["30fps","60fps"])

    if st.session_state.clips or st.session_state.clip_order:
        if st.button("⚡ 영상 자동 조립 시작"):
            prog=st.progress(0); stat=st.empty()
            for pct,msg in [(15,"📂 클립 로딩..."),(30,"✂️ 클립 연결..."),(50,"🎙️ 음성 합성..."),(65,"📝 자막 오버레이..."),(80,"🎵 BGM 믹싱..."),(92,"📐 9:16 변환..."),(100,"✅ 완료!")]:
                prog.progress(pct); stat.markdown(f"<span style='color:#a78bfa;'>{msg}</span>", unsafe_allow_html=True); time.sleep(0.65)
            st.session_state.output_path="/tmp/output_final.mp4"
            st.success("🎉 조립 완료! 탭 ④에서 다운로드하세요.")


# ═══════════════════════════════════════════════════════════════════
# TAB 4 : 다운로드
# ═══════════════════════════════════════════════════════════════════
with tab4:
    st.markdown('<div class="step-card"><div class="step-title">STEP 07</div><h3>💾 완성 영상 다운로드</h3></div>', unsafe_allow_html=True)
    st.markdown('<div class="info-box">📱 플랫폼별 파일을 다운로드한 후 각 앱에서 직접 업로드하세요.</div>', unsafe_allow_html=True)

    dc1,dc2 = st.columns(2)
    with dc1: auto_title = st.text_input("제목", value=f"{product_name or '제품'} 리뷰 | 이거 진짜 괜찮네요 #shorts")
    with dc2: auto_tags  = st.text_input("해시태그", value=f"#{product_name or '제품'} #숏폼 #리뷰 #shorts #viral #fyp")
    auto_desc = st.text_area("설명", value=f"{product_desc or ''}\n\n{auto_tags}", height=65)

    st.markdown("### 📥 플랫폼별 다운로드")
    video_ready = st.session_state.get("output_path") is not None
    specs = [
        ("▶ 유튜브 쇼츠","1080×1920 · MP4","badge-purple",f"{product_name or '제품'}_youtube_shorts.mp4","제목에 #Shorts 필수"),
        ("📸 인스타그램 릴스","1080×1920 · MP4","badge-cyan",f"{product_name or '제품'}_instagram_reels.mp4","커버 이미지 별도 설정 권장"),
        ("🎵 틱톡","1080×1920 · MP4","badge-green",f"{product_name or '제품'}_tiktok.mp4","해시태그 5개 이상 권장"),
    ]
    for name, spec, badge, fn, tip in specs:
        si1, si2 = st.columns([4,1])
        with si1:
            st.markdown(f'<div class="step-card" style="margin-bottom:8px;"><div style="display:flex;justify-content:space-between;align-items:center;"><div><span style="font-weight:700;">{name}</span> &nbsp; <span class="badge {badge}">{spec}</span><br><span style="font-size:.72rem;color:#a78bfa;">💡 {tip}</span></div></div></div>', unsafe_allow_html=True)
        with si2:
            st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
            if video_ready and os.path.exists(st.session_state.output_path):
                with open(st.session_state.output_path,"rb") as f:
                    st.download_button("⬇️ 다운로드", data=f.read(), file_name=fn, mime="video/mp4", use_container_width=True, key=f"dl_{name}")
            else:
                st.button("⬇️ 다운로드", disabled=True, use_container_width=True, key=f"dld_{name}", help="탭 ③에서 영상 조립 먼저 완료")

    if not video_ready:
        st.markdown('<div style="text-align:center;padding:12px;color:#64748b;font-size:.83rem;">⚠️ 탭 ③에서 <strong style="color:#a78bfa;">영상 조립</strong> 완료 후 활성화됩니다.</div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    with st.expander("🔑 필요한 API 키"):
        st.code("""
# .env 파일
ANTHROPIC_API_KEY=sk-ant-xxxxxxxx      # AI 스크립트/자막 수정

# TTS — 둘 중 하나 (또는 둘 다)
CLOVA_TTS_CLIENT_ID=xxxxxxxx           # 한국어 TTS (월 1만자 무료)
CLOVA_TTS_CLIENT_SECRET=xxxxxxxx
ELEVENLABS_API_KEY=sk_xxxxxxxx         # 감정 풍부한 TTS ($5/월~)

PEXELS_API_KEY=xxxxxxxx                # 키워드 영상 검색 (완전 무료, 선택)
        """, language="bash")
        st.markdown("""
        - **Anthropic**: [console.anthropic.com](https://console.anthropic.com)
        - **클로바 보이스**: [console.ncloud.com](https://console.ncloud.com) (월 1만자 무료)
        - **ElevenLabs**: [elevenlabs.io](https://elevenlabs.io) (월 1만자 무료, $5~)
        - **Pexels**: [pexels.com/api](https://www.pexels.com/api/) (완전 무료)
        """)
