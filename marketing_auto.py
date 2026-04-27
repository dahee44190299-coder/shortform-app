"""마케팅 자동화 — 본 도구의 사용 자체가 마케팅이 되는 자가 증식 루프.

전략 변경 (2026-04-27):
  광고 채널 막힘 + Phase 0 GTM 가설 실패 → 콘텐츠 마케팅으로 전환.
  사용자가 매출을 내는 순간 = 우리의 가장 강력한 마케팅 자산.

3가지 자동화:
  1. 케이스 스터디 자동 생성 (마크다운 → SEO 페이지)
  2. SNS 포스트 자동 작성 (X/스레드 형식)
  3. 매출 통계 집계 → 랜딩 페이지 자동 업데이트 ("최근 7일간 사용자 매출 합계")

데이터 소스: project_store.list_all_tracking_records() — 이미 구축됨.
출력: marketing/case_studies/, marketing/social_posts/ 디렉토리.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import project_store


MARKETING_DIR = "marketing"


def _ensure_dir(sub: str = "") -> Path:
    p = Path(MARKETING_DIR) / sub if sub else Path(MARKETING_DIR)
    p.mkdir(parents=True, exist_ok=True)
    return p


def aggregate_sales_stats(days: int = 7) -> dict:
    """집계: 모든 사용자/프로젝트의 최근 N일 매출.

    Returns:
        {
            "period_days": int,
            "total_videos": int,
            "total_clicks": int,
            "total_revenue_krw": int,
            "top_categories": [(cat, revenue), ...],
            "best_performer": {video_id, project_name, title, revenue},
        }
    """
    records = project_store.list_all_tracking_records()
    cutoff = None
    if days and days > 0:
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    filtered = []
    for r in records:
        ts = r.get("created_at", "")
        if cutoff and ts:
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt < cutoff:
                    continue
            except (ValueError, TypeError):
                pass
        filtered.append(r)

    total_clicks = sum(int(r.get("manual_clicks", 0) or 0) for r in filtered)
    total_revenue = sum(int(r.get("manual_revenue_krw", 0) or 0) for r in filtered)
    cat_revenue: dict = {}
    for r in filtered:
        cat = r.get("category") or r.get("template") or "general"
        cat_revenue[cat] = cat_revenue.get(cat, 0) + int(r.get("manual_revenue_krw", 0) or 0)
    top_cats = sorted(cat_revenue.items(), key=lambda x: -x[1])[:5]

    best = None
    if filtered:
        best_rec = max(filtered, key=lambda r: int(r.get("manual_revenue_krw", 0) or 0))
        if int(best_rec.get("manual_revenue_krw", 0) or 0) > 0:
            best = {
                "video_id": best_rec.get("video_id"),
                "project_name": best_rec.get("project_name", ""),
                "title": best_rec.get("title", ""),
                "revenue": int(best_rec.get("manual_revenue_krw", 0) or 0),
                "clicks": int(best_rec.get("manual_clicks", 0) or 0),
            }
    return {
        "period_days": days,
        "total_videos": len(filtered),
        "total_clicks": total_clicks,
        "total_revenue_krw": total_revenue,
        "top_categories": top_cats,
        "best_performer": best,
    }


def generate_case_study(record: dict) -> str:
    """추적 레코드 1건 → 마크다운 케이스 스터디 페이지.

    SEO 친화적 제목 + 구조화된 본문 + 자체 도구 cross-promotion.
    """
    title = record.get("title", "(영상)")
    project = record.get("project_name", "")
    sub_id = record.get("sub_id", "")
    clicks = int(record.get("manual_clicks", 0) or 0)
    revenue = int(record.get("manual_revenue_krw", 0) or 0)
    created = record.get("created_at", "")[:10]
    url = record.get("shorten_url") or record.get("original_url", "")

    ctr_str = ""
    if clicks > 0:
        ctr_str = f"\n클릭당 매출: **{revenue // clicks:,}원**"

    return f"""# {title} — 쿠팡 파트너스 영상 1개로 {revenue:,}원 매출

> *케이스 스터디: {project} · {created}*

## 결과 요약
- 추적 ID: `{sub_id}`
- 클릭 수: **{clicks:,}회**
- 매출: **{revenue:,}원**{ctr_str}

## 무엇이 효과적이었나
이 영상은 [shortform-app](https://github.com/dahee44190299-coder/shortform-app)의
**카테고리 가이드 + LLM judge** 시스템으로 생성됐습니다.

- 카테고리별 검증된 Hook 패턴 자동 적용
- LLM judge가 0-100점 평가 → 80점 미만 자동 재생성 (최대 3회)
- 추적 subId 자동 부착으로 영상별 매출 귀속

## 영상 보기
👉 {url}

## 직접 만들어보기
이 도구는 오픈소스입니다. 쿠팡 URL만 있으면 5분 안에 같은 결과를 만들 수 있어요.

```bash
git clone https://github.com/dahee44190299-coder/shortform-app
cd shortform-app
pip install -r requirements.txt
streamlit run app.py
```

---
*Generated automatically by shortform-app marketing pipeline.*
"""


def generate_social_post(stats: dict) -> str:
    """X/스레드 형식 짧은 포스트 (280자 한국어 약 140자)."""
    rev = stats["total_revenue_krw"]
    vids = stats["total_videos"]
    days = stats["period_days"]
    if rev > 0:
        return (
            f"📊 최근 {days}일간 shortform-app 사용자 누적 매출: {rev:,}원\n"
            f"영상 {vids}개로 클릭 {stats['total_clicks']:,}회.\n\n"
            f"카테고리 가이드 + LLM judge로 자동 생성한 영상이 실제 매출을 만들었습니다.\n"
            f"오픈소스: github.com/dahee44190299-coder/shortform-app\n"
            f"#쿠팡파트너스 #숏폼자동화 #AI"
        )
    # 매출 0인 경우: 빌드 인 퍼블릭 톤
    return (
        f"🛠️ shortform-app 빌드 인 퍼블릭 — Day N\n"
        f"최근 {days}일간 영상 {vids}개 자동 생성, "
        f"클릭 {stats['total_clicks']:,}회 누적.\n\n"
        f"매출은 아직 추적 중. 다음 주 결과 공개 예정.\n"
        f"github.com/dahee44190299-coder/shortform-app\n"
        f"#쿠팡파트너스 #BuildInPublic"
    )


def export_case_studies(min_revenue: int = 1) -> list:
    """매출 발생한 모든 추적 레코드 → 마크다운 파일로 저장.

    Returns: 생성된 파일 경로 리스트.
    """
    out_dir = _ensure_dir("case_studies")
    records = project_store.list_all_tracking_records()
    paths = []
    for r in records:
        if int(r.get("manual_revenue_krw", 0) or 0) < min_revenue:
            continue
        sub_id = r.get("sub_id", "no_id")
        fname = f"{r.get('created_at', '')[:10]}_{sub_id}.md"
        path = out_dir / fname
        path.write_text(generate_case_study(r), encoding="utf-8")
        paths.append(str(path))
    return paths


def export_landing_stats(days: int = 7) -> str:
    """랜딩 페이지용 stats.json 생성. 정적 사이트 빌드 시 활용."""
    stats = aggregate_sales_stats(days=days)
    out = _ensure_dir() / "landing_stats.json"
    out.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(out)


def export_social_post(days: int = 7) -> str:
    """소셜 포스트 1건 생성 (수동 검토 후 발행)."""
    stats = aggregate_sales_stats(days=days)
    text = generate_social_post(stats)
    out_dir = _ensure_dir("social_posts")
    fname = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + ".txt"
    out = out_dir / fname
    out.write_text(text, encoding="utf-8")
    return str(out)


if __name__ == "__main__":
    # CLI: python marketing_auto.py
    print("=== 마케팅 자동화 실행 ===")
    stats = aggregate_sales_stats(days=7)
    print(f"\n7일 통계:")
    print(f"  영상: {stats['total_videos']}개")
    print(f"  클릭: {stats['total_clicks']:,}")
    print(f"  매출: {stats['total_revenue_krw']:,}원")

    cases = export_case_studies(min_revenue=1)
    print(f"\n케이스 스터디 {len(cases)}건 생성:")
    for p in cases[:5]:
        print(f"  - {p}")

    landing = export_landing_stats(days=7)
    print(f"\n랜딩 stats: {landing}")

    social = export_social_post(days=7)
    print(f"소셜 포스트: {social}")
