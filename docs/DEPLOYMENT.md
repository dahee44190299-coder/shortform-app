# 🚀 배포 & 수익화 가이드

> 본 프로젝트를 실제 사용자에게 서비스하는 가장 빠른 경로.

---

## TL;DR — 추천 스택

```
[랜딩 페이지]           [영상 생성 앱]              [결제]
Vercel (Next.js)  →  Streamlit Cloud  →  PortOne (한국) 또는 Stripe
       ↓                      ↑                     ↑
   유입 (SEO)            (case study CTA)        (Pro 전환)
```

**총 비용 (월)**:
- Vercel: $0 (Hobby) ~ $20 (Pro)
- Streamlit Cloud: $0 (Community) ~ $30 (Teams)
- PortOne: 결제 수수료만 (2.9% + ₩300/건)
- 도메인: ₩15,000/년 (1만원대)

→ **사용자 0명 구간: 거의 $0**, 매출 발생 시 자동 비례.

---

## Streamlit Cloud — 영상 생성 앱

### 왜 Streamlit Cloud?
- 공식 (Streamlit사가 운영)
- GitHub 저장소 자동 연동 → push마다 자동 배포
- 무료 (Community tier, 1GB RAM, 1 CPU)
- secrets.toml 직접 업로드 (UI에서)
- HTTPS 자동

### 단점
- 콜드 스타트 5-10초
- 동시 사용자 많아지면 느림 (Pro tier 필요)
- 외부 IP 고정 안 됨 (쿠팡 API 화이트리스트 못 함 — 단, 쿠팡 Open API는 IP 제한 없음)

### 배포 단계

1. **GitHub에 push** (이미 완료)
2. https://share.streamlit.io 가입 + GitHub 연결
3. "New app" → 저장소 선택 → `app.py` 지정
4. Advanced settings → **Secrets**에 `.streamlit/secrets.toml` 내용 붙여넣기:
   ```toml
   ANTHROPIC_API_KEY = "sk-ant-..."
   PEXELS_API_KEY = ""
   # ... 나머지
   ```
5. Deploy → 5분 후 `https://your-app.streamlit.app` 접속 가능

### packages.txt
시스템 패키지 (이미 저장소에 포함):
```
ffmpeg
fonts-nanum
```

### requirements.txt
이미 작성됨. Streamlit Cloud가 자동 설치.

---

## Vercel — 랜딩 페이지 + 케이스 스터디

### 왜 Vercel?
- Next.js 공식 호스팅 (SEO 최적화 자동)
- 무료 + 자동 HTTPS + 글로벌 CDN
- GitHub push마다 preview deploy
- Edge Functions로 동적 데이터 가능

### 디렉토리 구조 (별도 저장소 권장)

```
shortform-app-landing/
├── app/
│   ├── page.tsx                    # 메인 랜딩
│   ├── case/[slug]/page.tsx        # 케이스 스터디 동적 라우트
│   └── pricing/page.tsx
├── content/
│   └── case-studies/*.md           # marketing_auto.py가 자동 생성
└── package.json
```

### 케이스 스터디 자동 발행 흐름

```
[Streamlit 앱]
    ↓ 사용자가 매출 입력
[marketing_auto.export_case_studies()]
    ↓ 마크다운 파일 생성
[GitHub Actions cron — 매주 일요일]
    ↓ marketing/case_studies/*.md → Vercel 저장소로 PR
[Vercel 자동 deploy]
    ↓ shortform-app.dev/case/{slug}
[SEO 트래픽 유입]
    ↓ 무료 가입 → Pro 전환
[$$$]
```

---

## 결제 — 한국 vs 글로벌

### 한국 시장 우선이면: **PortOne** (구 아임포트)

```python
# Python SDK 예시 (대시보드에서 결제 위젯 띄움)
import portone

portone.subscribe_create(
    customer_uid="user_123",
    merchant_uid="pro_subscription",
    amount=9900,
    name="shortform-app Pro 월 구독",
)
```

**장점**:
- 카카오페이/네이버페이/토스페이 통합
- 카드 결제 (모든 한국 카드사)
- 한국 사업자 등록 + 통신판매신고 필요
- 수수료 2.9% + ₩300

**대안**: Toss Payments (개발자 친화적, 더 깔끔한 SDK)

### 글로벌이면: **Stripe**

**장점**:
- 모든 통화 + 자동 환율
- 자동 부가세 계산 (EU VAT 등)
- 구독/일회성/사용량 기반 모두 지원

**단점**:
- 한국 사업자 등록 필요 (Stripe Korea)
- 한국 카카오페이 미지원

### 둘 다 하려면: **Lemon Squeezy** (Merchant of Record)

- 본인 사업자 등록 불필요 (Lemon Squeezy가 판매자)
- 글로벌 부가세 자동 처리
- 수수료 5% + Stripe 수수료
- 빠른 시작에 최고

---

## 인증 — 사용자 식별

### 옵션 비교

| 도구 | 가격 | 한국 카카오 로그인 | 추천 시점 |
|---|---|---|---|
| **Streamlit auth (간단 토큰)** | $0 | ❌ | MVP, 베타 |
| **Supabase Auth** | $0 (5만 MAU) | ✅ (커스텀) | 100명+ |
| **Clerk** | $0 (1만 MAU) | ⚠️ (커스텀) | 빠른 출시 |
| **Auth0** | $0 (7천 MAU) | ⚠️ | 엔터프라이즈 |
| **카카오 로그인 직접 연동** | $0 | ✅ | 한국 특화 |

**추천 (한국)**: Supabase Auth + 카카오 OAuth

---

## 분석 — 무엇을 측정할까

| 지표 | 도구 | 측정 방법 |
|---|---|---|
| 가입자 | DB | `SELECT COUNT(*) FROM users` |
| 영상 생성 수 | project_store | `list_all_tracking_records()` |
| 활성 사용자 (WAU/MAU) | PostHog 또는 Plausible | 자동 |
| Pro 전환율 | Stripe + DB | `paid_users / total_users` |
| 이탈 (Churn) | Stripe | 자동 |
| LLM judge 평균 점수 | eval_metrics | `compute_stats()` |

**추천**:
- **Plausible** ($9/월) — 한국 GDPR 친화, 가벼움
- **PostHog** — 셀프호스팅 가능, A/B 테스트 포함
- **Stripe Dashboard** — 결제 분석은 Stripe로 충분

---

## 도메인 + DNS

1. **가비아** 또는 **Cloudflare Registrar** (가격 비슷)
2. `shortform-app.dev` 추천 (`.com`은 비싸고 자주 선점됨, `.dev`는 저렴 + HTTPS 강제)
3. Vercel/Streamlit Cloud 모두 커스텀 도메인 무료 지원
4. CNAME 설정만 하면 5분 안에 적용

---

## 보안 체크리스트 (출시 전)

- [ ] secrets.toml은 절대 git에 안 올라감 (`.gitignore` 확인)
- [ ] API 키는 Streamlit Cloud Secrets에만 입력 (코드 X)
- [ ] 사용자 입력 sanitize (XSS 방지) — Streamlit이 기본적으로 처리
- [ ] LLM 호출 rate limit (사용자당 분당 10회 등)
- [ ] 결제 webhook 서명 검증 (Stripe/PortOne 모두 제공)
- [ ] 개인정보 처리방침 + 이용약관 페이지 (한국 법적 필수)
- [ ] 사업자 등록 + 통신판매업 신고 (월 매출 100만원 초과 시)

---

## 출시 전 마지막 체크

1. **가격 결정**: Free / $9 / $29 / 매출 5% revenue share 중 어떤 조합?
2. **결제 수단**: 카카오/네이버페이 필요? → PortOne. 글로벌만? → Stripe.
3. **첫 사용자 모집**: Build in Public로 본인 케이스 스터디 먼저 발행
4. **로드맵 공개**: GitHub README + 랜딩 페이지에 명시 (신뢰도)

---

## 가장 빠른 출시 경로 (1주 내)

### Day 1-2: Streamlit Cloud 배포
- secrets.toml 업로드
- 도메인 연결 (선택)
- 첫 영상 1개 본인이 직접 생성 → 스크린샷

### Day 3-4: 랜딩 페이지 (Vercel)
- Astro 또는 Next.js 템플릿 1개 가져와 수정
- 첫 케이스 스터디 1건 발행
- 가입 폼 (이메일만 받기, 결제는 나중)

### Day 5: Build in Public 시작
- X(트위터) 한국 부업/인디해커 커뮤니티에 글
- "오픈소스로 쿠팡 파트너스 영상 자동화 도구 만들었어요"
- GitHub 링크 + Streamlit Cloud 링크

### Day 6-7: 피드백 수집 + PMF 설문
- pmf_survey.py로 in-product NPS 측정
- 첫 10명 가입자 인터뷰 (1:1, 20분)
- Pro 가격 검증 ($9 vs $29 vs revenue share)

→ **2주차에 첫 결제 받는 게 목표**.
