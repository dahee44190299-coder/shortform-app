# 🔍 코드 리뷰 + 파이프라인 검토 + 운영 가이드

> 운영자가 **코드 몰라도 안전하게 운영** 가능하도록 작성된 가이드.

---

## 1. 코드베이스 현황 (2026-04-29 기준)

### 모듈 구조 (총 10,400줄)

| 모듈 | 줄 | 역할 | 안정성 |
|---|---|---|---|
| **`app.py`** | 5,547 | 메인 UI + 영상 파이프라인 | ⚠️ (분리 필요) |
| `project_store.py` | 404 | 저장소 facade (JSON/SQLite) | ✅ |
| `project_store_sqlite.py` | 345 | SQLite 백엔드 | ✅ |
| `whitelist.py` | 327 | Founder + 초대 코드 | ✅ |
| `viral_patterns.py` | 282 | 12개 viral 패턴 | ✅ |
| `script_judge.py` | 254 | LLM 평가 + 자동 재생성 | ✅ |
| `tracking.py` | 249 | 추적 링크 + CSV 파싱 | ✅ |
| `voice_match.py` | 242 | 본인 톤 학습 (NEW) | ✅ |
| `competitor_dna.py` | 241 | 경쟁사 영상 DNA (NEW) | ✅ |
| `constants.py` | 229 | 상수 데이터 | ✅ |
| `eval_metrics.py` | 225 | LLM 호출 메트릭 | ✅ |
| `clip_analyzer.py` | 225 | FFmpeg 영상 분석 | ✅ |
| `marketing_auto.py` | 225 | 케이스 스터디 자동 발행 | ✅ |
| `youtube_uploader.py` | 221 | YouTube 업로드 (NEW) | ✅ |
| `admin_dashboard.py` | 215 | 관리자 페이지 | ✅ |
| `script_prompts.py` | 186 | 마스터 프롬프트 | ✅ |
| `use_cases.py` | 174 | 4개 use case | ✅ |
| `category_templates.py` | 167 | 카테고리별 가이드 | ✅ |
| `run_eval.py` | 151 | 평가 CLI | ✅ |
| `pmf_survey.py` | 139 | PMF 설문 | ✅ |
| `stock_video.py` | 131 | Pexels + YouTube 검색 | ✅ |
| `regeneration.py` | 115 | 저성과 재생성 | ✅ |
| `scripts/compare_guide_impact.py` | 104 | LLM A/B 비교 | ✅ |
| `llm.py` | 76 | call_claude 래퍼 | ✅ |
| `api_keys.py` | 27 | API 키 액세스 | ✅ |
| **테스트** | (별도) | **199 passing** | ✅ |

---

## 2. 발견된 코드 이슈 (P0~P3)

### 🔴 P0 — 즉시 처리 필요
없음. (모든 P0는 이전 PR들에서 처리됨)

### 🟡 P1 — 다음 sprint
1. **`app.py` 5,547줄 단일 파일** — 분리 진행 중 (이미 14개 모듈로 분리)
   - 남은 분리 후보: `video_pipeline.py` (FFmpeg 합성), `streamlit_views.py` (STEP 1-4 함수들)
2. **25개 `bare except:`** — 디버깅 어려움. 구체적 예외로 변경 필요
3. **session_state 일관성** — `st.session_state["x"]` vs `st.session_state.x` 혼재 (영향 0, 가독성만)

### 🟢 P2 — 시간 날 때
4. JSON 백엔드 1개 `bare except:` (project_store.py 1개)
5. 일부 모듈 type hints 누락
6. `_scripts/` 디렉토리 미사용 import 정리

### 🔵 P3 — 선택적 개선
7. mypy/pyright 통과율 95% (의존성 false positive 제외)

---

## 3. 영상 생성 파이프라인 (End-to-End)

```
┌──────────────────────────────────────────────────┐
│  1. STEP 1 — 소스 입력                            │
│  ┌─────────────────────────────┐                 │
│  │ 쿠팡 공유 텍스트 ─→ parse_share│                │
│  │ 또는 URL ─→ extract_coupang_info│             │
│  │ 또는 경쟁사 URL ─→ DNA 추출    │ ← USP        │
│  │ 카테고리 자동 추론             │                │
│  └─────────────────────────────┘                 │
└──────────────────┬───────────────────────────────┘
                   │
┌──────────────────▼───────────────────────────────┐
│  2. STEP 2 — 영상 클립                            │
│  ┌─────────────────────────────┐                 │
│  │ Pexels 자동 검색 (한→영 번역)  │                │
│  │ 또는 YouTube 검색 (yt-dlp 폴백)│                │
│  │ 또는 사용자 업로드            │                │
│  │ FFmpeg 자동 클립 분할 (장면 감지)│              │
│  └─────────────────────────────┘                 │
└──────────────────┬───────────────────────────────┘
                   │
┌──────────────────▼───────────────────────────────┐
│  3. STEP 3 — AI 대본 (핵심 차별화)                │
│  ┌─────────────────────────────┐                 │
│  │ 카테고리 가이드 자동 주입       │                │
│  │ + viral 패턴 3가지 동시 생성   │ ← Pika 차별점   │
│  │ + DNA 적용 (경쟁사 분석 시)    │ ← USP          │
│  │ + 본인 톤 매칭 (프로필 있을 시) │ ← USP NEW      │
│  │ → script_judge 0-100 평가     │                │
│  │ → 점수 < 85 자동 재생성 (3회)  │                │
│  │ Edge TTS / ElevenLabs 음성    │                │
│  │ ASS 자막 자동 생성             │                │
│  └─────────────────────────────┘                 │
└──────────────────┬───────────────────────────────┘
                   │
┌──────────────────▼───────────────────────────────┐
│  4. STEP 4 — 추적 + 다운로드 + 업로드              │
│  ┌─────────────────────────────┐                 │
│  │ FFmpeg 합성 (영상+음성+자막)   │                │
│  │ 추적 링크 subId 자동 (또는 수동)│                │
│  │ 해시태그 + 설명란 자동           │                │
│  │ 다운로드 (MP4)                  │                │
│  │ YouTube Shorts 자동 업로드 (NEW)│ ← Klap 차별점  │
│  │ 추적 레코드 → SQLite/JSON 저장  │                │
│  └─────────────────────────────┘                 │
└──────────────────┬───────────────────────────────┘
                   │
┌──────────────────▼───────────────────────────────┐
│  5. 매출 회수 + 마케팅 자동화                      │
│  ┌─────────────────────────────┐                 │
│  │ 추적 대시보드 (영상별 매출)     │                │
│  │ CSV 업로드 → subId 자동 매칭   │                │
│  │ 주간 GitHub Actions cron:     │                │
│  │   ─→ 케이스 스터디 자동 발행   │                │
│  │   ─→ 소셜 포스트 자동 작성    │                │
│  │ PMF 설문 자동 노출            │                │
│  └─────────────────────────────┘                 │
└──────────────────────────────────────────────────┘
```

### 파이프라인 의존성 매트릭스

| 단계 | 필수 키 | 폴백 | 실패 시 영향 |
|---|---|---|---|
| 대본 생성 | ANTHROPIC_API_KEY | 없음 | AI 기능 비활성화 (수동 입력 가능) |
| 음성 | (없음) | Edge TTS 자동 | 항상 동작 ✅ |
| 자막 | (없음) | FFmpeg ASS | 항상 동작 ✅ |
| Pexels | PEXELS_API_KEY | yt-dlp | 검색 비활성, 수동 업로드 OK |
| YouTube 검색 | YOUTUBE_API_KEY | yt-dlp | 자동 폴백 ✅ |
| 추적 링크 | COUPANG_PARTNERS_* | subId만 생성 | 수동 적용 안내 |
| **자동 업로드** | YOUTUBE_OAUTH_* | (없음) | 수동 업로드 가능 |
| 매출 추적 | (없음) | CSV 업로드 | 항상 동작 ✅ |

→ **단 1개 키(ANTHROPIC_API_KEY)** 만 있으면 핵심 기능 모두 작동.

---

## 4. 운영자가 알아야 할 것 (간소화 가이드)

### A. 일상 운영 — 매주 5분이면 됨

#### 매주 일요일 (자동)
- GitHub Actions가 09:00 KST 자동 실행
- `marketing_auto.py` → 케이스 스터디 + 소셜 포스트 자동 생성
- → GitHub PR 자동 생성됨
- **운영자 액션**: PR 검토 → 머지 (1분)

#### 매주 1회 (수동)
- Streamlit Cloud 앱 살아있는지 확인 (https://shortform-app-ter35ed68uufcdvjrmd7om.streamlit.app)
- 관리자 페이지 → PMF 설문 결과 확인 (NPS, 결제 의향)
- → GO/NO_GO 판정 자동 표시

### B. 사용자 추가 — 30초

```
1. Shorts AI Studio 접속
2. 사이드바 → user_id에 본인 이메일 (이미 등록됨)
3. 관리자 페이지 → 🎫 초대 코드 발급 → 메모 입력 → 발급
4. 받은 코드 (INV-XXXX-XXXX) 친구에게 카톡 전달
5. 친구는: 사이드바 → user_id 입력 → 코드 입력 → 등록 완료
```

### C. 문제 발생 시 — 디버깅 트리

```
앱이 안 열림
├─ Streamlit Cloud 사이트 접속 → Manage app → Logs 확인
├─ 빨간 에러 있으면 → 마지막 commit 롤백 (git revert)
└─ 빈 화면 → "Reboot app" 클릭

대본 생성 안 됨
├─ ANTHROPIC_API_KEY 잔액 확인 (console.anthropic.com)
├─ Streamlit Cloud Secrets에 키 있는지 확인
└─ 데모 모드로 돌아감 (수동 스크립트 입력 가능)

영상 합성 실패
├─ FFmpeg 오류 → 클립 길이/포맷 확인
├─ 메모리 부족 → 클립 수 줄이기 (최대 5개 권장)
└─ 자막 한글 깨짐 → fonts-nanum 확인

YouTube 업로드 실패
├─ 401 → OAuth 재인증 (사이드바 → YouTube 연동)
├─ 일 한도 초과 → 다음날 (무료 6개)
└─ Sandbox 모드 → Google Cloud Console에서 publish
```

### D. 비용 모니터링

| 항목 | 확인 위치 | 한도 |
|---|---|---|
| **Anthropic Sonnet 4.5** | console.anthropic.com → Usage | 영상 1개 ≈ $0.04 (3 변형) |
| Streamlit Cloud | share.streamlit.io | Free 티어 (1GB RAM) |
| GitHub Actions | github.com → Actions | Free 티어 (월 2000분) |
| YouTube API | console.cloud.google.com | 무료 (일 6 영상) |
| Pexels | pexels.com/api | 무료 (월 200 요청) |

→ **월 사용 추정**: 영상 100개 = $4 = 약 5,500원 (가장 큰 비용)

### E. 백업 — 데이터 손실 방지

```bash
# 매주 한 번 (자동화 가능)
# Streamlit Cloud는 영속 저장 보장 X (재배포 시 데이터 사라질 수 있음)
# → 중요 데이터는 GitHub로 백업

cd shortform-app
# shortform_projects 디렉토리는 .gitignore되어 있음
# 백업 필요한 파일:
zip -r backup_$(date +%Y%m%d).zip shortform_projects/

# 또는 SQLite로 전환 후 DB 파일만 백업
SHORTFORM_DB=sqlite python project_store.py  # 마이그레이션
# → shortform_projects/projects.db
```

---

## 5. 운영 체크리스트 (운영자 입장)

### 🟢 매일 (1분)
- [ ] 앱 살아있나? → 사이드바 user_id 입력해보기

### 🟢 매주 (10분)
- [ ] PMF 설문 결과 확인 (관리자 페이지)
- [ ] Anthropic 사용량 확인 (console)
- [ ] GitHub Actions 자동 PR 검토 + 머지
- [ ] 1주일 내 매출 발생 사용자 인터뷰 (1명)

### 🟡 매월 (1시간)
- [ ] 케이스 스터디 페이지 SEO 확인 (Search Console)
- [ ] 사용자별 retention 분석 (활성 사용자 수)
- [ ] 가격 정책 검증 (Pro 전환율 vs 자유 사용)
- [ ] 비용 vs 매출 ROI 점검

### 🔴 분기별 (반나절)
- [ ] 코드 의존성 업데이트 (`pip install -U`)
- [ ] 보안 감사 (API 키 노출 여부)
- [ ] 백업 데이터 복원 테스트
- [ ] 경쟁사 분석 업데이트 (`docs/MARKET_ANALYSIS.md`)

---

## 6. 즉시 실행 가능한 작업 — "오늘 할 수 있는 것"

### 🥇 매출 발생 1순위 (난이도 낮음, 효과 높음)
1. **본인이 직접 영상 1개 만들어 SNS 업로드** (1시간)
2. **첫 친구 1명 초대** (5분, 초대 코드 발급)
3. **Build in Public 첫 글** (X/디스코드, 30분)

### 🥈 차별화 (난이도 중간)
4. **본인 톤 학습** — 본인 글 5개 → voice_match에 등록 (10분)
5. **잘된 영상 3개 DNA 분석** — 경쟁사 분석 (10분)
6. **자동 업로드 OAuth 등록** — Google Cloud Console (30분)

### 🥉 시스템 (난이도 높음)
7. **TikTok API 베타 신청** (대기열, 1-2주)
8. **첫 케이스 스터디 작성** (실제 매출 발생 후)

---

## 7. 진짜 한 줄 요약

**"운영자가 코드 한 줄도 안 봐도 되도록 설계됨."**

- 사용자 추가: 사이드바 클릭 5번
- 매출 회수: CSV 업로드 1번
- 마케팅: 매주 자동 PR 머지 1번
- 비용 관리: console.anthropic.com 한 페이지
- 문제 진단: Streamlit Cloud Logs 한 페이지

**100% 코드 무관 운영 가능.** ✅
