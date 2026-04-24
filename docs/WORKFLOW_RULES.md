# 📋 Workflow Rules — 순차 작업 규칙

이 문서는 [IMPROVEMENT_PLAN.md](IMPROVEMENT_PLAN.md)를 따라 작업할 때 지켜야 할 운영 규칙이다.

---

## 🚦 0. 절대 규칙

1. **Go/No-Go 게이트 위반 금지**: 직전 Phase 측정 결과가 기준 미달이면 다음 Phase 진입 금지.
2. **Phase 0 중 코드 변경 금지**: 검증 단계에 기능 추가하면 검증값 오염됨.
3. **모든 가설은 정량 측정으로만 종결**: "느낌상 좋다"로 다음 단계 진입 금지.

---

## 🌿 1. 브랜치 전략

```
main                    ← 항상 배포 가능 상태
  ├─ docs/*             ← 문서 변경
  ├─ feat/*             ← 새 기능
  ├─ fix/*              ← 버그 수정
  ├─ refactor/*         ← 리팩토링
  └─ phase{N}/{task}    ← 특정 Phase의 작업
       예: phase0/interview-kit
           phase1/tracking-link
           phase2/oauth-lockin
```

### 브랜치 생성 → 머지 흐름
```bash
# 1. 작업 브랜치 생성
git checkout main && git pull
git checkout -b phase0/interview-kit

# 2. 작업 → 커밋 → 푸시
git add <files>
git commit -m "type: 한 줄 요약"
git push -u origin phase0/interview-kit

# 3. 묶인 작업이 끝나면 main으로 병합
git checkout main
git merge phase0/interview-kit --no-ff -m "Merge phase0/interview-kit"
git push origin main
```

### 커밋 메시지 컨벤션 (기존 commit 스타일 유지)
```
type: 한 줄 요약 (한국어 OK)

상세 설명 (선택)
- 변경 사유
- 영향 범위

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

`type` 종류: `feat / fix / refactor / docs / test / chore / phase{N}`

---

## 📊 2. Phase 진입 체크리스트

### Phase 0 → Phase 1 진입 조건
- [ ] 인터뷰 5명 완료 + 노트 5개
- [ ] 베타 신청 ≥ 30명
- [ ] 베타 사용자 결제 의향 ≥ 30%
- [ ] "우리 게 낫다" 답변 ≥ 50%
- [ ] 회고 문서 작성 (`docs/phase0/RETROSPECTIVE.md`)

### Phase 1 → Phase 2 진입 조건
- [ ] 영상 생성 수 / 유저 ≥ 5개/주
- [ ] 영상→업로드 전환율 ≥ 60%
- [ ] WAU/MAU ≥ 50%
- [ ] NPS ≥ 40
- [ ] 코드: app.py 모듈 분리 완료
- [ ] 회고 문서

### Phase 2 → Phase 3 진입 조건
- [ ] 누적 영상 데이터 ≥ 10,000개
- [ ] AI 추천 적용군 매출 +X% 통계적 유의성
- [ ] 채널 OAuth 연동률 ≥ 70%
- [ ] SQLite/Postgres 마이그레이션 완료
- [ ] 회고 문서

---

## 🔁 3. 매주 리듬

| 요일 | 작업 |
|---|---|
| 월 | 주간 KPI 측정 + Notion에 기록 |
| 화~목 | 작업 (Phase 별 task) |
| 금 | 회고 + 다음 주 계획 |
| 매월 마지막 금 | 가설 점검 (현재 가설 vs 데이터) |

---

## 📦 4. 산출물 위치 (모두 `docs/` 하위)

```
docs/
├─ IMPROVEMENT_PLAN.md         ← 전략 마스터 플랜
├─ WORKFLOW_RULES.md           ← 본 문서
├─ phase0/
│   ├─ INTERVIEW_SCRIPT.md     ← 인터뷰 질문지
│   ├─ INTERVIEW_TEMPLATE.md   ← 인터뷰 노트 템플릿
│   ├─ BETA_RECRUITMENT.md     ← 베타 모집 글 + 채널
│   ├─ METRICS_TRACKING.md     ← 측정 지표 + 데이터 수집 표
│   └─ RETROSPECTIVE.md        ← Phase 종료 회고 (Phase 종료 시 작성)
├─ phase1/                     ← Phase 1 진입 시 생성
├─ phase2/
└─ phase3/
```

---

## 🛑 5. 중단 신호 (Stop & Pivot)

다음 신호 중 하나라도 발생하면 **즉시 작업 중단 + 회의**:

1. Phase 0 결제 의향 < 20% (재정의 신호)
2. 단일 유저 일별 사용 시간 평균 < 5분 (도구로 안 쓰는 중)
3. 30일 이탈률 > 50% (가치 전달 실패)
4. 쿠팡/플랫폼 약관 위반 사례 발생 (법적 리스크)
5. 경쟁사가 우리 핵심 기능 무료 제공 (해자 무력화)

→ **Stop & Pivot 시**: `docs/PIVOT_LOG.md` 작성 + 가설 재정의

---

## 🤖 6. AI 협업 규칙 (이 프로젝트 한정)

- 모든 코드 변경은 **테스트 가능한 수준의 PR 단위**로 분리
- 한 PR = 한 가지 변경 (혼합 금지)
- 자동 생성 코드는 커밋 메시지에 `🤖 Generated with [Claude Code]` 명시
- LLM 호출하는 코드는 **반드시 평가 데이터셋 50개로 회귀 테스트** (Phase 1-C 이후)
