"""project_store_sqlite.py 단위 테스트 — SQLite 백엔드.

JSON 백엔드 테스트(test_project_store.py)와 동일 시나리오 + SQLite 특화 검증.
"""
import json

import pytest

import project_store_sqlite as store


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """각 테스트가 별도 임시 DB."""
    fake_dir = tmp_path / "shortform_projects"
    fake_dir.mkdir()
    monkeypatch.setattr(store, "PROJECTS_DIR", str(fake_dir))
    return fake_dir


class TestSchemaInit:
    def test_db_file_created_on_first_call(self, isolated_db):
        assert store.list_projects() == []
        assert (isolated_db / "projects.db").exists()

    def test_idempotent_init(self, isolated_db):
        # 여러 번 호출해도 안전
        store.list_projects()
        store.list_projects()
        store.list_projects()


class TestProjectCrud:
    def test_create_and_get(self, isolated_db):
        pid = store.create_project("배수구 테스트", product_name="X",
                                    category="생활용품", template="문제해결형")
        assert pid.startswith("prj_")
        d = store.get_project(pid)
        assert d["name"] == "배수구 테스트"
        assert d["category"] == "생활용품"
        assert d["videos"] == []

    def test_list_returns_dicts(self, isolated_db):
        store.create_project("A")
        store.create_project("B")
        ps = store.list_projects()
        assert len(ps) == 2
        assert {"id", "name", "created_at", "template", "video_count"}.issubset(ps[0].keys())

    def test_update(self, isolated_db):
        pid = store.create_project("원본")
        ok = store.update_project(pid, name="수정", template="리뷰형")
        assert ok
        assert store.get_project(pid)["name"] == "수정"

    def test_update_unknown_field_ignored(self, isolated_db):
        pid = store.create_project("p")
        # 'evil' 필드는 화이트리스트에 없음 → 업데이트 호출 자체가 False 반환
        # (sets가 비어있으므로 0개 필드 업데이트)
        result = store.update_project(pid, evil="hack")
        assert result is False

    def test_update_nonexistent(self, isolated_db):
        assert store.update_project("nonexistent", name="x") is False

    def test_delete_cascade_videos_and_tracking(self, isolated_db):
        pid = store.create_project("p")
        store.add_video_version(pid, "v")
        store.add_tracking_record(pid, {"video_id": "vx", "sub_id": "s"})
        assert store.delete_project(pid)
        assert store.get_project(pid) is None
        # 외래키 ON DELETE CASCADE
        assert store.list_video_versions(pid) == []
        assert store.list_tracking_records(pid) == []


class TestVideos:
    def test_add_and_list(self, isolated_db):
        pid = store.create_project("p")
        v1 = store.add_video_version(pid, "Hook A", hook_type="problem",
                                       pattern_interrupt=False,
                                       retention_booster=True,
                                       tts_engine="elevenlabs")
        assert v1
        vs = store.list_video_versions(pid)
        assert len(vs) == 1
        assert vs[0]["pattern_interrupt_enabled"] is False
        assert vs[0]["retention_booster_enabled"] is True
        assert vs[0]["downloaded"] is False

    def test_add_to_unknown_project_returns_none(self, isolated_db):
        assert store.add_video_version("prj_zzz", "x") is None

    def test_mark_downloaded(self, isolated_db):
        pid = store.create_project("p")
        vid = store.add_video_version(pid, "x")
        assert store.mark_downloaded(pid, vid)
        v = store.get_video_version(pid, vid)
        assert v["downloaded"] is True


class TestTracking:
    def test_add_overwrites_same_video_id(self, isolated_db):
        pid = store.create_project("p")
        store.add_tracking_record(pid, {"video_id": "v1", "sub_id": "old"})
        store.add_tracking_record(pid, {"video_id": "v1", "sub_id": "new"})
        recs = store.list_tracking_records(pid)
        assert len(recs) == 1
        assert recs[0]["sub_id"] == "new"

    def test_add_to_unknown_project_returns_false(self, isolated_db):
        assert store.add_tracking_record("prj_zzz", {"video_id": "v"}) is False

    def test_update_metrics_with_uploaded_to(self, isolated_db):
        pid = store.create_project("p")
        store.add_tracking_record(pid, {"video_id": "v1", "manual_clicks": 0})
        ok = store.update_tracking_metrics(
            pid, "v1", manual_clicks=99, manual_revenue_krw=50000,
            uploaded_to=["youtube", "tiktok"]
        )
        assert ok
        rec = store.list_tracking_records(pid)[0]
        assert rec["manual_clicks"] == 99
        assert rec["manual_revenue_krw"] == 50000
        assert rec["uploaded_to"] == ["youtube", "tiktok"]

    def test_uploaded_to_serialized_as_json(self, isolated_db):
        pid = store.create_project("p")
        store.add_tracking_record(pid, {
            "video_id": "v1",
            "uploaded_to": ["a", "b", "c"],
        })
        rec = store.list_tracking_records(pid)[0]
        assert rec["uploaded_to"] == ["a", "b", "c"]

    def test_list_all_includes_project_name(self, isolated_db):
        p1 = store.create_project("프로젝트1")
        p2 = store.create_project("프로젝트2")
        store.add_tracking_record(p1, {"video_id": "v1"})
        store.add_tracking_record(p2, {"video_id": "v2"})
        recs = store.list_all_tracking_records()
        assert len(recs) == 2
        names = {r["project_name"] for r in recs}
        assert names == {"프로젝트1", "프로젝트2"}


class TestMigrationFromJson:
    def test_migration_full_roundtrip(self, isolated_db, tmp_path, monkeypatch):
        """JSON 파일 → migrate → SQLite 검증."""
        # 1) JSON 파일 직접 생성 (project_store.py 사용 안 함, 격리 위해)
        prj_id = "prj_test1"
        prj_dir = isolated_db / prj_id
        prj_dir.mkdir()
        (prj_dir / "project.json").write_text(json.dumps({
            "id": prj_id,
            "name": "마이그레이션 테스트",
            "created_at": "2026-04-24T00:00:00",
            "product_name": "P",
            "category": "생활용품",
            "template": "문제해결형",
            "workspace_id": "",
            "videos": [{
                "version_id": "v_old1",
                "name": "기존 영상",
                "hook_type": "problem",
                "pattern_interrupt_enabled": True,
                "retention_booster_enabled": False,
                "tts_engine": "edge",
                "video_path": "/tmp/x.mp4",
                "downloaded": True,
                "created_at": "2026-04-24T01:00:00",
            }],
            "tracking": [{
                "video_id": "v_old1",
                "sub_id": "vid_xxx",
                "shorten_url": "https://link.coupang.com/x",
                "manual_clicks": 17,
                "manual_revenue_krw": 8500,
                "uploaded_to": ["youtube"],
                "original_url": "https://coupang.com/p",
                "created_at": "2026-04-24T01:00:00",
            }]
        }, ensure_ascii=False), encoding="utf-8")

        # 2) 마이그레이션 실행
        import project_store as ps_facade
        monkeypatch.setattr(ps_facade, "PROJECTS_DIR", str(isolated_db))
        result = ps_facade.migrate_json_to_sqlite(verbose=False)
        assert result["projects"] == 1
        assert result["videos"] == 1
        assert result["tracking"] == 1

        # 3) SQLite에서 조회
        d = store.get_project(prj_id)
        assert d["name"] == "마이그레이션 테스트"
        assert d["category"] == "생활용품"
        assert len(d["videos"]) == 1
        assert d["videos"][0]["downloaded"] is True
        assert d["videos"][0]["pattern_interrupt_enabled"] is True
        assert d["videos"][0]["retention_booster_enabled"] is False

        recs = store.list_tracking_records(prj_id)
        assert len(recs) == 1
        assert recs[0]["sub_id"] == "vid_xxx"
        assert recs[0]["manual_clicks"] == 17
        assert recs[0]["uploaded_to"] == ["youtube"]

    def test_migration_idempotent(self, isolated_db, monkeypatch):
        """같은 데이터를 두 번 마이그레이션해도 중복 안 만들어짐."""
        prj_id = "prj_dup"
        prj_dir = isolated_db / prj_id
        prj_dir.mkdir()
        (prj_dir / "project.json").write_text(json.dumps({
            "id": prj_id, "name": "중복 테스트",
            "created_at": "2026-04-24T00:00:00",
            "videos": [], "tracking": [],
        }), encoding="utf-8")

        import project_store as ps_facade
        monkeypatch.setattr(ps_facade, "PROJECTS_DIR", str(isolated_db))

        r1 = ps_facade.migrate_json_to_sqlite(verbose=False)
        r2 = ps_facade.migrate_json_to_sqlite(verbose=False)
        assert r1["projects"] == 1
        assert r2["projects"] == 0
        assert r2["skipped"] == 1
