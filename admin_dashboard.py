"""관리자 페이지 — Founder 전용 통합 대시보드.

표시 정보:
  1. 전체 통계 (영상/매출/조회/클릭/사용자)
  2. 사용자 티어 분포 (Founder/Invitee/Pro/Free)
  3. LLM judge 점수 추이 (eval_metrics)
  4. PMF 설문 결과 (NPS + 결제 의향)
  5. 마케팅 자동화 현황 (케이스 스터디 발행 수)
  6. 시스템 헬스 (LLM 호출 비용 추정)
  7. Founder 관리 + 초대 코드 관리
"""
from pathlib import Path

import eval_metrics
import pmf_survey
import project_store
import whitelist


def get_admin_stats() -> dict:
    """관리자 대시보드용 통합 통계."""
    # 전체 추적 레코드
    all_records = project_store.list_all_tracking_records()

    # use case별 분포
    by_uc: dict = {}
    by_tier: dict = {"founder": 0, "invitee": 0, "pro": 0, "free": 0}

    total_clicks = sum(int(r.get("manual_clicks", 0) or 0) for r in all_records)
    total_revenue = sum(int(r.get("manual_revenue_krw", 0) or 0) for r in all_records)
    total_views = sum(int(r.get("manual_views", 0) or 0) for r in all_records)
    total_likes = sum(int(r.get("manual_likes", 0) or 0) for r in all_records)
    total_subs = sum(int(r.get("manual_subscribers", 0) or 0) for r in all_records)

    for r in all_records:
        uc = r.get("use_case", "coupang_affiliate")
        by_uc[uc] = by_uc.get(uc, 0) + 1

    # 사용자 티어 (founders + invitees)
    founders = whitelist.list_founders()
    invitees = whitelist.list_invitees()
    by_tier["founder"] = len(founders)
    by_tier["invitee"] = len(invitees)
    # paid_pro/free는 결제 시스템 통합 후 측정 가능

    # LLM 호출 통계 (7일/30일)
    stats_7d = eval_metrics.compute_stats(days=7)
    stats_30d = eval_metrics.compute_stats(days=30)

    # PMF 설문 집계
    pmf = pmf_survey.aggregate_nps_and_payment_intent()

    # 마케팅 발행 현황
    case_dir = Path("marketing/case_studies")
    case_count = len(list(case_dir.glob("*.md"))) if case_dir.exists() else 0
    social_dir = Path("marketing/social_posts")
    social_count = len(list(social_dir.glob("*.txt"))) if social_dir.exists() else 0

    # 비용 추정 (Sonnet 4.5 평균 단가 기반)
    # input ~$3/M, output ~$15/M, 평균 호출당 약 $0.005-0.015
    est_cost_30d_usd = stats_30d["count"] * 0.008 if stats_30d["count"] else 0

    return {
        "total_videos": len(all_records),
        "total_clicks": total_clicks,
        "total_revenue_krw": total_revenue,
        "total_views": total_views,
        "total_likes": total_likes,
        "total_subscribers": total_subs,
        "by_use_case": by_uc,
        "by_tier": by_tier,
        "founders": founders,
        "invitees": invitees,
        "llm_stats_7d": stats_7d,
        "llm_stats_30d": stats_30d,
        "pmf": pmf,
        "marketing": {
            "case_studies_published": case_count,
            "social_posts_drafted": social_count,
        },
        "est_llm_cost_30d_usd": round(est_cost_30d_usd, 2),
        "est_llm_cost_30d_krw": int(est_cost_30d_usd * 1400),  # 환율 추정
    }


def render_admin_page(st_module):
    """Streamlit으로 관리자 페이지 렌더.

    Args:
        st_module: streamlit 모듈 (앱 안에서 호출 시 import 순환 방지)
    """
    st = st_module
    st.markdown("# 👑 관리자 페이지")
    st.caption("Founder 전용. 전체 시스템 현황 및 사용자/마케팅/비용 관리.")

    stats = get_admin_stats()

    # ── 1. 핵심 지표 ──
    st.markdown("### 📊 핵심 지표 (전체 사용자 합계)")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("영상", f"{stats['total_videos']:,}개")
    c2.metric("매출", f"{stats['total_revenue_krw']:,}원")
    c3.metric("클릭/조회", f"{stats['total_clicks'] + stats['total_views']:,}")
    c4.metric("LLM 비용 (30일)", f"₩{stats['est_llm_cost_30d_krw']:,}")

    # ── 2. Use Case 분포 ──
    if stats["by_use_case"]:
        st.markdown("### 🎯 Use Case별 영상 수")
        uc_cols = st.columns(len(stats["by_use_case"]))
        for i, (uc, count) in enumerate(stats["by_use_case"].items()):
            label_map = {
                "coupang_affiliate": "🛒 쿠팡",
                "general_affiliate": "🌍 기타",
                "youtube_review": "📹 리뷰",
                "personal_vlog": "🎬 브이로그",
            }
            uc_cols[i].metric(label_map.get(uc, uc), f"{count}개")

    # ── 3. 사용자 티어 ──
    st.markdown("### 👥 사용자 티어")
    tc1, tc2, tc3, tc4 = st.columns(4)
    tc1.metric("👑 Founders", stats["by_tier"]["founder"])
    tc2.metric("✨ Invitees", stats["by_tier"]["invitee"])
    tc3.metric("💎 Pro (결제)", stats["by_tier"]["pro"])
    tc4.metric("🆓 Free", "측정 중")

    # ── 4. PMF ──
    st.markdown("### 🎯 PMF 진단")
    pmf = stats["pmf"]
    pc1, pc2, pc3 = st.columns(3)
    pc1.metric("응답 수", pmf["n"])
    pc2.metric("NPS", pmf["nps_score"])
    pc3.metric("결제 의향", f"{pmf['would_pay_pct']}%")
    decision = pmf["go_no_go"]
    decision_color = {
        "GO": "🟢",
        "NO_GO": "🔴",
        "NEED_MORE_DATA": "🟡",
    }.get(decision, "🟡")
    st.markdown(f"**판정**: {decision_color} **{decision}** "
                f"(n≥10 + would_pay≥30% + promoters≥30% → GO)")

    # ── 5. LLM 품질 ──
    st.markdown("### 🤖 LLM 호출 품질 (7일)")
    llm = stats["llm_stats_7d"]
    if llm["count"] == 0:
        st.caption("아직 LLM 호출 기록 없음")
    else:
        lc1, lc2, lc3 = st.columns(3)
        lc1.metric("호출 수", llm["count"])
        lc2.metric("Hook 포함률", f"{llm['metrics']['has_hook_pct']}%")
        lc3.metric("CTA 포함률", f"{llm['metrics']['has_cta_pct']}%")
        st.caption(f"평균 글자: {llm['metrics']['char_len']['mean']} · "
                   f"평균 지연: {llm['latency_ms']['mean']}ms")

    # ── 6. 마케팅 자동화 ──
    st.markdown("### 📢 마케팅 자동화 현황")
    mc1, mc2 = st.columns(2)
    mc1.metric("케이스 스터디 발행", stats["marketing"]["case_studies_published"])
    mc2.metric("소셜 포스트 초안", stats["marketing"]["social_posts_drafted"])
    st.caption("매주 일요일 09:00 KST GitHub Actions 자동 실행 → "
               "PR로 발행 (검토 후 머지)")

    # ── 7. Founder 관리 ──
    st.markdown("### 👑 Founder 관리")
    for f in stats["founders"]:
        cols = st.columns([3, 1, 1])
        cols[0].markdown(f"- **{f['user_id']}** "
                          f"({f.get('source', 'file')}, "
                          f"{f.get('note', '')})")
        if f.get("source") == "file" and len(stats["founders"]) > 1:
            if cols[2].button("🗑️", key=f"rm_founder_{f['user_id']}",
                                help="founder 권한 철회"):
                if whitelist.remove_founder(f["user_id"]):
                    st.success("철회됨")
                    st.rerun()

    new_founder = st.text_input("새 Founder 추가", placeholder="email@example.com",
                                  key="_admin_new_founder")
    note = st.text_input("메모 (선택)", placeholder="예: 공동창업자",
                          key="_admin_new_founder_note")
    if st.button("➕ Founder 추가", key="btn_add_founder"):
        if new_founder.strip():
            r = whitelist.add_founder(new_founder.strip(),
                                        added_by="admin_ui", note=note)
            if r["ok"]:
                st.success(r["reason"])
                st.rerun()
            else:
                st.error(r["reason"])

    # ── 8. 초대 코드 관리 ──
    st.markdown("### 🎫 초대 코드 관리")
    icols = st.columns([3, 1, 1])
    inv_note = icols[0].text_input("발급 메모", placeholder="베타 사용자 김XX",
                                     key="_admin_invite_note")
    inv_max = icols[1].number_input("사용 횟수", min_value=1, max_value=100,
                                      value=1, key="_admin_invite_max")
    if icols[2].button("발급", key="btn_admin_gen_invite", type="primary"):
        code = whitelist.generate_invite_code(
            created_by="admin_ui", note=inv_note, max_uses=inv_max
        )
        st.session_state["_admin_last_code"] = code
        st.rerun()

    if st.session_state.get("_admin_last_code"):
        st.code(st.session_state["_admin_last_code"], language="")

    invitees = whitelist.list_invitees()
    if invitees:
        with st.expander(f"등록된 사용자 ({len(invitees)}명)"):
            for inv in invitees:
                st.markdown(f"- **{inv['user_id']}** · "
                            f"{inv.get('via_code', '')} · "
                            f"{inv.get('note', '')}")
