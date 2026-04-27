# 🎬 숏폼 자동화 제작기

> 쿠팡 파트너스 · 쇼핑몰 홍보 · 틱톡 리뷰 — AI 기반 숏폼 영상 자동 생성 파이프라인

제품 URL 하나로 **영상 소스 확보 → 클립 편집 → AI 대본·자막·음성 → 다운로드**까지 원스톱으로 처리합니다.

---

## 📁 프로젝트 구조

```
shortform_app/
├── app.py                       # 메인 앱 (Streamlit UI + 파이프라인)
├── clip_analyzer.py             # FFmpeg 장면 감지 + 자동 클립 분할
│
├── project_store.py             # 저장소 facade (env로 JSON/SQLite 백엔드 선택)
├── project_store_sqlite.py      # SQLite 백엔드 (Phase 2 멀티유저/분석)
│
├── api_keys.py                  # API 키 액세스 (Streamlit secrets + env 폴백)
├── llm.py                       # call_claude (Anthropic) + 자동 메트릭 로깅
├── stock_video.py               # Pexels + YouTube + yt-dlp 검색
├── tracking.py                  # 쿠팡 추적 링크 (subId/deeplink)
├── category_templates.py        # 카테고리별 검증된 Hook/구조/CTA
├── regeneration.py              # 저성과 영상 자동 감지 + 재생성 추천
├── eval_metrics.py              # LLM 호출 편차 측정 (JSONL 누적)
├── constants.py                 # TEMPLATES, CTA_LIBRARY 등 상수 데이터
│
├── run_eval.py                  # 카테고리 추론 정확도 평가 CLI
├── eval_data/eval_cases.json    # 50 케이스 평가 데이터셋
├── tests/                       # 87 unit tests + 2 e2e (수동)
├── .github/workflows/tests.yml  # CI: pytest + 카테고리 정확도 게이트
│
├── requirements.txt
├── packages.txt
├── pytest.ini
└── shortform_projects/          # 프로젝트 데이터
    ├── projects.db              # SQLite (SHORTFORM_DB=sqlite 시)
    ├── _metrics/llm_calls.jsonl # LLM 호출 로그
    └── {project_id}/
        └── project.json         # JSON 백엔드 (기본)
```

### 저장 백엔드 전환 (JSON → SQLite)

```bash
# 1) 기존 JSON 데이터 마이그레이션 (idempotent — 여러 번 실행 OK)
python project_store.py

# 2) 환경변수로 SQLite 활성화
# Linux/Mac:
export SHORTFORM_DB=sqlite
# Windows PowerShell:
$env:SHORTFORM_DB = "sqlite"

# 3) 앱 재시작
streamlit run app.py
```
SQLite는 멀티유저 동시 접근 + SQL 집계 + 트랜잭션을 제공합니다 (Phase 2 데이터 해자의 인프라).

---

## 🗺️ 메뉴 트리

```
숏폼 자동화 제작기
│
├── 🏠 프로젝트 선택 (app_phase: project_select)
│   ├── 📋 기존 프로젝트 목록
│   │   ├── 프로젝트 열기
│   │   └── 프로젝트 삭제
│   ├── ➕ 새 프로젝트 생성
│   └── 🎓 온보딩 카드 (초보자용 가이드)
│       └── 🛒→🎬→✂️→🤖→📥 플로우 시각화
│
├── 📐 템플릿 선택 (app_phase: template_select)
│   ├── 🛒 쿠팡 쇼츠 — 파트너스 특화, 3초 Hook + CTA
│   ├── 🏪 쇼핑몰 제품 홍보 — 혜택 강조 + 구매 유도
│   ├── 📱 틱톡 리뷰 — 솔직 리뷰, 놀람 Hook
│   └── 🔧 문제 해결 광고 — 문제→해결 구조
│
├── STEP 1: 🛒 소스 선택 (current_step: 1)
│   ├── Block 1: 📦 제품 정보
│   │   ├── 쿠팡 URL 입력 → OG 태그 자동 크롤링
│   │   ├── 제품명 / 카테고리 수동 입력
│   │   ├── 제품 이미지 추출
│   │   └── 제품 영상 추출
│   ├── 🔎 추천 영상 찾기 (YouTube)
│   │   ├── 🔍 추천 영상 검색 (AI 키워드 → YouTube)
│   │   ├── 결과 카드 (썸네일·제목·채널·길이·조회수)
│   │   └── ✅ 이 영상 사용 → 다운로드 + AutoClip 분할
│   ├── Block 2: 🎬 영상 확보
│   │   ├── 소스 타입 선택: URL / 업로드 / YouTube / Pexels
│   │   ├── Pexels 스톡 영상 검색 (AI 키워드 추천)
│   │   ├── YouTube Shorts 검색
│   │   ├── 틱톡/인스타/더우인 URL 다운로드
│   │   └── Ken Burns 이미지 → 영상 변환
│   └── Block 3: 🛠️ 참고 도구
│       ├── AI 트렌드 키워드 분석
│       └── OG 태그 결과 표시
│
├── STEP 2: ✂️ 클립 편집 (current_step: 2)
│   ├── 클립 카드 목록
│   │   ├── ↑↓ 순서 이동
│   │   ├── 용도 태그 (인트로 / 제품소개 / 사용장면 / 아웃트로)
│   │   ├── 소스 뱃지 (Pexels / KenBurns / Upload / auto_split)
│   │   └── ❌ 클립 삭제
│   └── 요약: 총 클립 수 · 총 재생 시간
│
├── STEP 3: 🤖 영상 생성 (current_step: 3)
│   ├── 🎯 조회수 최적화 패널
│   │   ├── 🪝 Hook A/B/C 테스트 (2~3 버전)
│   │   ├── ⚡ Pattern Interrupt (시각 효과)
│   │   ├── 🛡️ Anti-Shadowban 딥에디팅
│   │   └── 📈 Retention Booster (시청 지속)
│   ├── 📝 제목 생성 (AI 9개, 다양한 스타일)
│   ├── 📝 대본 생성
│   │   ├── 콘텐츠 모드: 클릭유도형 / 구매전환형 / 리뷰형 / 문제해결형
│   │   ├── AI 스크립트 생성 (Claude)
│   │   └── 스크립트 편집 / 버전 히스토리
│   ├── 🪝 후킹 문구 생성 (5개)
│   ├── 🗣️ TTS 음성 생성
│   │   ├── 엔진 선택: ElevenLabs / Naver Clova
│   │   └── 속도 조절
│   ├── 🎨 자막 생성
│   │   ├── AI 자동 타이밍 생성
│   │   ├── 자막 색상 / 크기 / 위치 / 애니메이션
│   │   └── 키워드 하이라이트
│   ├── 🎵 BGM 선택 (Pixabay)
│   │   ├── 카테고리별 자동 검색
│   │   └── 볼륨 조절
│   ├── 📐 CTA 오버레이 설정
│   └── 🎬 영상 조립 (FFmpeg)
│       ├── 단일 영상 생성
│       ├── Hook A/B/C 버전 생성
│       └── 🎲 Multi-Video 5개 자동 생성
│
├── STEP 4: 📥 다운로드 (current_step: 4)
│   ├── 1️⃣ 해시태그 자동 생성 (20개)
│   │   ├── AI 생성 (10개)
│   │   ├── 카테고리 DB (5개)
│   │   └── 공통 태그 (5개)
│   ├── 2️⃣ 썸네일 자동 생성
│   │   ├── 메인 텍스트 / 서브 텍스트
│   │   └── 제품 이미지 오버레이
│   ├── 3️⃣ 영상 다운로드
│   │   ├── 단일 영상 / Hook 버전 / Multi-Video 결과
│   │   └── 설명란 자동 생성 (AI)
│   └── 🔑 API 키 가이드
│
└── 사이드바
    ├── 프로젝트 정보 표시
    ├── 템플릿 정보 표시
    ├── STEP 네비게이션
    └── 프로젝트 목록으로 돌아가기
```

---

## ⚙️ 파이프라인 흐름도

```
┌─────────────────────────────────────────────────────────────┐
│                    STEP 1: 소스 선택                         │
│                                                             │
│  쿠팡 URL ──→ OG태그 크롤링 ──→ 제품명 · 카테고리 자동 입력  │
│                  │                                          │
│                  ├──→ 제품 이미지 추출                       │
│                  └──→ 제품 영상 추출                         │
│                                                             │
│  영상 소스 확보:                                             │
│    ├── YouTube 추천 검색 (AI 키워드 → youtube-search-python) │
│    ├── Pexels 스톡 영상 (AI 키워드 → Pexels API)            │
│    ├── YouTube Shorts 검색                                  │
│    ├── 틱톡/더우인 URL (yt-dlp + douyin-scraper fallback)   │
│    ├── 직접 업로드                                          │
│    └── 제품 이미지 → Ken Burns 영상 변환 (FFmpeg)            │
│                                                             │
│  AutoClip: analyze_scenes() → split_clips() → 자동 분할     │
└───────────────────────────┬─────────────────────────────────┘
                            │ clips[]
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    STEP 2: 클립 편집                         │
│                                                             │
│  clips[] ──→ ↑↓ 순서 조정                                   │
│          ──→ 용도 태그 (인트로/제품소개/사용장면/아웃트로)     │
│          ──→ 불필요 클립 삭제                                │
│          ──→ auto_order_clips() 자동 정렬                    │
└───────────────────────────┬─────────────────────────────────┘
                            │ ordered clips[]
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    STEP 3: 영상 생성                         │
│                                                             │
│  ┌─ AI 콘텐츠 생성 (Claude) ─────────────────────────────┐  │
│  │  제목 9개 생성 (숫자형/질문형/감탄형/비유형/명령형)     │  │
│  │  대본 생성 (콘텐츠 모드별 프롬프트)                     │  │
│  │  후킹 문구 5개 생성                                    │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─ 음성 · 자막 ─────────────────────────────────────────┐  │
│  │  TTS: ElevenLabs / Naver Clova                        │  │
│  │  자막: ASS 포맷 (색상 · 위치 · 애니메이션 · 하이라이트) │  │
│  │  BGM: Pixabay Music API                               │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─ 조회수 최적화 ───────────────────────────────────────┐  │
│  │  Hook A/B/C: 3초 후킹 + TTS + 자막 별도 조립          │  │
│  │  Pattern Interrupt: 줌/점프컷/키워드강조/플래시         │  │
│  │  Retention Booster: 동적 자막 · 시각 강조              │  │
│  │  Anti-Shadowban: 속도·밝기·미러·피치 미세 변조         │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─ FFmpeg 영상 조립 (assemble_video) ───────────────────┐  │
│  │  입력: clips + TTS + ASS자막 + BGM + CTA              │  │
│  │                                                        │  │
│  │  필터 체인:                                            │  │
│  │    crop(9:16) → [anti-shadowban] → subtitle(ASS)      │  │
│  │    → CTA오버레이 → PatternInterrupt → RetentionBoost  │  │
│  │                                                        │  │
│  │  오디오 믹싱:                                          │  │
│  │    TTS + BGM(볼륨조절) + [피치시프트]                   │  │
│  │                                                        │  │
│  │  출력 모드:                                            │  │
│  │    ├── 단일 영상 (1개)                                 │  │
│  │    ├── Hook A/B/C 버전 (2~3개)                         │  │
│  │    └── Multi-Video (5개 조합 자동 생성)                 │  │
│  └────────────────────────────────────────────────────────┘  │
└───────────────────────────┬─────────────────────────────────┘
                            │ output .mp4
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    STEP 4: 다운로드                          │
│                                                             │
│  해시태그 20개 (AI 10 + 카테고리 5 + 공통 5)                │
│  썸네일 자동 생성 (Pillow — 텍스트 오버레이 + 제품 이미지)   │
│  설명란 자동 생성 (AI)                                      │
│  영상 미리보기 + MP4 다운로드                                │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔧 핵심 기능

| 기능 | 설명 |
|------|------|
| **AutoClip** | FFmpeg 장면 감지로 영상 자동 분할 (`clip_analyzer.py`) |
| **YouTube 추천 검색** | 제품명 → AI 영어 키워드 → YouTube 검색 → 90초 이하 필터링 |
| **Multi-Video** | Hook A/B/C × Pattern Interrupt ON/OFF = 5개 영상 자동 생성 |
| **Hook A/B/C** | 3초 후킹 영상 2~3 버전 생성 (문제 제시 / 놀람 / 손실 회피) |
| **Pattern Interrupt** | 시청 중 시각 자극 (줌 · 점프컷 · 키워드 강조 · 플래시) |
| **Retention Booster** | 시청 지속율 향상 (동적 자막 강조 · 시각 효과) |
| **Anti-Shadowban** | 영상 고유성 확보 — 속도·밝기·미러·BGM 피치 미세 변조 |
| **AI 대본 생성** | Claude API로 4가지 콘텐츠 모드별 대본 자동 생성 |
| **TTS 이중 엔진** | ElevenLabs (다국어) + Naver Clova (한국어 특화) |
| **CTA 다양화** | 8개 카테고리별 CTA 풀에서 랜덤 선택 |
| **프로젝트 시스템** | JSON 기반 프로젝트 관리 + 비디오 버전 추적 |

---

## 🚀 설치 및 실행

### 사전 요구사항

- **Python** 3.9+
- **FFmpeg** ([다운로드](https://ffmpeg.org/download.html)) — PATH에 추가 필요

### 설치

```bash
git clone https://github.com/dahee44190299-coder/shortform-app.git
cd shortform-app
pip install -r requirements.txt
```

### API 키 설정

`.streamlit/secrets.toml` 파일을 만들고 아래 내용을 입력하세요:

```toml
ANTHROPIC_API_KEY = "sk-ant-..."        # AI 기능 (필수)
ELEVENLABS_API_KEY = "sk_..."           # TTS 음성 생성
PEXELS_API_KEY = "..."                  # 스톡 영상 검색
PIXABAY_API_KEY = "..."                 # BGM 음악 검색

# 선택: Naver Clova TTS
CLOVA_TTS_CLIENT_ID = "..."
CLOVA_TTS_CLIENT_SECRET = "..."
```

### 실행

```bash
streamlit run app.py
```

---

## 📦 의존성

| 패키지 | 용도 |
|--------|------|
| `streamlit` | 웹 UI 프레임워크 |
| `anthropic` | Claude AI API |
| `requests` | HTTP 요청 |
| `python-dotenv` | 환경변수 관리 |
| `Pillow` | 썸네일 이미지 생성 |
| `beautifulsoup4` | OG 태그 · 웹 스크래핑 |
| `yt-dlp` | 영상 다운로드 (YouTube · TikTok · Douyin) |
| `douyin-tiktok-scraper` | Douyin 전용 fallback 다운로더 |
| `youtube-search-python` | YouTube 추천 영상 검색 |

**시스템 패키지** (Streamlit Cloud): `ffmpeg`, `fonts-nanum`

---

## 📐 템플릿 시스템

| 템플릿 | Hook 타입 | CTA | TTS | 콘텐츠 모드 |
|--------|----------|-----|-----|------------|
| 🛒 쿠팡 쇼츠 | problem | 쿠팡에서 확인하기 | ElevenLabs | 구매전환형 |
| 🏪 쇼핑몰 홍보 | benefit | 지금 바로 구매하기 | ElevenLabs | 클릭유도형 |
| 📱 틱톡 리뷰 | surprise | 링크 클릭! | Clova | 리뷰형 |
| 🔧 문제 해결 | problem | 이거 하나면 해결 | ElevenLabs | 문제해결형 |

---

## 🏗️ 아키텍처

```
┌────────────────────────────────────────────┐
│              Streamlit UI Layer             │
│  render_step1~4() · render_project_select  │
│  render_template_select · _render_nav      │
└──────────────┬─────────────────────────────┘
               │
┌──────────────▼─────────────────────────────┐
│           Business Logic Layer              │
│  call_claude() · generate_tts_auto()       │
│  assemble_video() · assemble_hook_versions │
│  generate_hooks() · generate_ass_subtitle  │
│  generate_thumbnail() · search_pexels()    │
│  download_video_with_fallback()            │
│  search_youtube_recommendations()          │
└──────────────┬─────────────────────────────┘
               │
┌──────────────▼─────────────────────────────┐
│          External Services Layer            │
│  Claude API · ElevenLabs · Clova TTS       │
│  Pexels API · Pixabay API · YouTube Search │
│  yt-dlp · douyin-scraper                   │
└──────────────┬─────────────────────────────┘
               │
┌──────────────▼─────────────────────────────┐
│           Processing Layer                  │
│  FFmpeg (영상 조립 · 장면 감지 · 오디오)    │
│  Pillow (썸네일 생성)                       │
│  clip_analyzer.py (AutoClip)               │
│  project_store.py (JSON 저장)              │
└────────────────────────────────────────────┘
```

---

## 📝 카테고리

8개 제품 카테고리를 지원하며, 각 카테고리에 맞는 해시태그 · CTA · BGM 키워드 · Pexels 검색어가 자동 적용됩니다.

`생활용품` · `뷰티/화장품` · `전자기기` · `패션/의류` · `식품` · `건강/헬스` · `유아/키즈` · `기타`

---

## 📄 라이선스

이 프로젝트는 개인/학습 목적으로 제작되었습니다.
