"""project_store.py 단위 테스트 — JSON 저장 레이어 회귀 방지."""
import pytest

import project_store


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    """각 테스트가 별도 임시 디렉토리에서 동작."""
    fake = tmp_path / "shortform_projects"
    fake.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(project_store, "PROJECTS_DIR", str(fake))
    return str(fake)


class TestCrudCycle:
    def test_create_and_get(self, isolated_store):
        pid = project_store.create_project("배수구", product_name="냄새 제거기",
                                            category="생활용품", template="문제해결형")
        assert pid.startswith("prj_")
        data = project_store.get_project(pid)
        assert data["name"] == "배수구"
        assert data["product_name"] == "냄새 제거기"
        assert data["category"] == "생활용품"
        assert data["videos"] == []

    def test_list_projects(self, isolated_store):
        p1 = project_store.create_project("A")
        p2 = project_store.create_project("B")
        ids = {p["id"] for p in project_store.list_projects()}
        assert p1 in ids and p2 in ids

    def test_update_project(self, isolated_store):
        pid = project_store.create_project("원본")
        ok = project_store.update_project(pid, name="수정", template="리뷰형")
        assert ok is True
        d = project_store.get_project(pid)
        assert d["name"] == "수정"
        assert d["template"] == "리뷰형"

    def test_update_nonexistent_returns_false(self, isolated_store):
        assert project_store.update_project("prj_nonexistent", name="x") is False

    def test_delete(self, isolated_store):
        pid = project_store.create_project("삭제 테스트")
        assert project_store.get_project(pid) is not None
        assert project_store.delete_project(pid) is True
        assert project_store.get_project(pid) is None


class TestVideoVersions:
    def test_add_and_list(self, isolated_store):
        pid = project_store.create_project("p")
        v1 = project_store.add_video_version(pid, "Hook A")
        v2 = project_store.add_video_version(pid, "Hook B", hook_type="problem")
        assert v1 and v2
        versions = project_store.list_video_versions(pid)
        assert len(versions) == 2

    def test_mark_downloaded(self, isolated_store):
        pid = project_store.create_project("p")
        v = project_store.add_video_version(pid, "X")
        v_data = project_store.get_video_version(pid, v)
        assert v_data["downloaded"] is False
        project_store.mark_downloaded(pid, v)
        v_data = project_store.get_video_version(pid, v)
        assert v_data["downloaded"] is True


class TestTrackingRecords:
    def test_add_and_list(self, isolated_store):
        pid = project_store.create_project("p")
        rec = {
            "video_id": "v1", "project_id": pid,
            "sub_id": "vid_x", "shorten_url": "", "landing_url": "",
            "original_url": "https://coupang/x", "template": "", "title": "T",
            "created_at": "2026-04-24T00:00:00",
            "manual_clicks": 0, "manual_revenue_krw": 0, "uploaded_to": [],
        }
        ok = project_store.add_tracking_record(pid, rec)
        assert ok is True
        recs = project_store.list_tracking_records(pid)
        assert len(recs) == 1
        assert recs[0]["sub_id"] == "vid_x"

    def test_add_overwrites_same_video_id(self, isolated_store):
        pid = project_store.create_project("p")
        base = {"video_id": "v1", "project_id": pid, "sub_id": "old"}
        project_store.add_tracking_record(pid, base)
        new = {"video_id": "v1", "project_id": pid, "sub_id": "new"}
        project_store.add_tracking_record(pid, new)
        recs = project_store.list_tracking_records(pid)
        assert len(recs) == 1
        assert recs[0]["sub_id"] == "new"

    def test_update_metrics(self, isolated_store):
        pid = project_store.create_project("p")
        project_store.add_tracking_record(pid, {
            "video_id": "v1", "project_id": pid,
            "manual_clicks": 0, "manual_revenue_krw": 0, "uploaded_to": [],
        })
        ok = project_store.update_tracking_metrics(
            pid, "v1", manual_clicks=42, manual_revenue_krw=12000,
            uploaded_to=["youtube", "tiktok"],
        )
        assert ok is True
        rec = project_store.list_tracking_records(pid)[0]
        assert rec["manual_clicks"] == 42
        assert rec["manual_revenue_krw"] == 12000
        assert rec["uploaded_to"] == ["youtube", "tiktok"]

    def test_list_all_aggregates_across_projects(self, isolated_store):
        p1 = project_store.create_project("A")
        p2 = project_store.create_project("B")
        project_store.add_tracking_record(p1, {"video_id": "v1", "project_id": p1})
        project_store.add_tracking_record(p2, {"video_id": "v2", "project_id": p2})
        all_recs = project_store.list_all_tracking_records()
        assert len(all_recs) == 2
        for r in all_recs:
            assert "project_name" in r
