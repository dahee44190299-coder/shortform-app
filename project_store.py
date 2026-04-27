"""
프로젝트 저장 레이어 (JSON 파일 기반 MVP)

구조:
  shortform_projects/
    {project_id}/
      project.json          ← 프로젝트 메타 + 비디오 버전 목록

설계 원칙:
  - 모든 I/O를 이 파일 안 함수로 캡슐화
  - 추후 SQLite / Firebase / DB로 교체 시 이 파일만 교체하면 됨
  - Streamlit Cloud 배포 환경에서는 영속 저장이 보장되지 않음 (로컬 MVP 전용)
  - 향후 Workspace 확장 가능: project.json에 workspace_id 필드 예약

스키마:
  project.json = {
    "id": "prj_xxx",
    "name": "배수구 냄새 제거기",
    "created_at": "2026-03-09T12:00:00",
    "workspace_id": "",          ← 향후 Workspace 확장용
    "product_name": "",
    "category": "",
    "template": "",
    "videos": [
      {
        "version_id": "v_A",
        "name": "Hook A - 문제 제시",
        "hook_type": "problem",
        "pattern_interrupt_enabled": true,
        "retention_booster_enabled": true,
        "tts_engine": "elevenlabs",
        "video_path": "",
        "created_at": "2026-03-09T12:05:00",
        "downloaded": false
      }
    ]
  }
"""

import json
import os
import time
from pathlib import Path

PROJECTS_DIR = "shortform_projects"

# ── 백엔드 선택 (Phase 2 SQLite 마이그레이션) ─────────────────────
# 환경변수 SHORTFORM_DB=sqlite 면 모든 호출을 project_store_sqlite로 위임.
# 기본값은 JSON (하위 호환). 마이그레이션은 migrate_json_to_sqlite() 사용.
_USE_SQLITE = os.getenv("SHORTFORM_DB", "").lower() == "sqlite"

if _USE_SQLITE:
    import project_store_sqlite as _sqlite
    # PROJECTS_DIR을 양쪽 모듈에 동기화 (테스트 격리용)
    _sqlite.PROJECTS_DIR = PROJECTS_DIR


def _ensure_projects_dir():
    os.makedirs(PROJECTS_DIR, exist_ok=True)


def _project_dir(project_id):
    return os.path.join(PROJECTS_DIR, project_id)


def _project_json_path(project_id):
    return os.path.join(_project_dir(project_id), "project.json")


def _read_project_file(project_id):
    path = _project_json_path(project_id)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_project_file(project_id, data):
    d = _project_dir(project_id)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "project.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════════
# Public API — 추후 DB 교체 시 이 함수 시그니처만 유지하면 됨
# ═══════════════════════════════════════════════════════════════

def list_projects():
    """모든 프로젝트 목록 반환. [{id, name, created_at, template, video_count}, ...]"""
    _ensure_projects_dir()
    projects = []
    if not os.path.exists(PROJECTS_DIR):
        return projects
    for name in sorted(os.listdir(PROJECTS_DIR)):
        pj = os.path.join(PROJECTS_DIR, name, "project.json")
        if os.path.isfile(pj):
            try:
                with open(pj, "r", encoding="utf-8") as f:
                    data = json.load(f)
                projects.append({
                    "id": data.get("id", name),
                    "name": data.get("name", name),
                    "created_at": data.get("created_at", ""),
                    "template": data.get("template", ""),
                    "video_count": len(data.get("videos", [])),
                })
            except:
                pass
    return projects


def create_project(name, product_name="", category="", template=""):
    """새 프로젝트 생성. project_id 반환."""
    _ensure_projects_dir()
    project_id = f"prj_{int(time.time() * 1000)}"
    data = {
        "id": project_id,
        "name": name,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "workspace_id": "",
        "product_name": product_name,
        "category": category,
        "template": template,
        "videos": [],
    }
    _write_project_file(project_id, data)
    return project_id


def get_project(project_id):
    """프로젝트 전체 데이터 반환. 없으면 None."""
    return _read_project_file(project_id)


def update_project(project_id, **kwargs):
    """프로젝트 메타데이터 업데이트. (name, product_name, category, template)"""
    data = _read_project_file(project_id)
    if not data:
        return False
    for k, v in kwargs.items():
        if k in ("name", "product_name", "category", "template", "workspace_id"):
            data[k] = v
    _write_project_file(project_id, data)
    return True


def delete_project(project_id):
    """프로젝트 삭제 (디렉토리 포함)."""
    import shutil
    d = _project_dir(project_id)
    if os.path.exists(d):
        shutil.rmtree(d, ignore_errors=True)
        return True
    return False


def add_video_version(project_id, name, hook_type="", pattern_interrupt=True,
                      retention_booster=True, tts_engine="elevenlabs", video_path=""):
    """프로젝트에 비디오 버전 추가. version_id 반환."""
    data = _read_project_file(project_id)
    if not data:
        return None
    version_id = f"v_{int(time.time() * 1000)}"
    version = {
        "version_id": version_id,
        "name": name,
        "hook_type": hook_type,
        "pattern_interrupt_enabled": pattern_interrupt,
        "retention_booster_enabled": retention_booster,
        "tts_engine": tts_engine,
        "video_path": video_path,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "downloaded": False,
    }
    data.setdefault("videos", []).append(version)
    _write_project_file(project_id, data)
    return version_id


def list_video_versions(project_id):
    """프로젝트의 모든 비디오 버전 목록."""
    data = _read_project_file(project_id)
    if not data:
        return []
    return data.get("videos", [])


def get_video_version(project_id, version_id):
    """특정 비디오 버전 데이터."""
    for v in list_video_versions(project_id):
        if v.get("version_id") == version_id:
            return v
    return None


def mark_downloaded(project_id, version_id):
    """비디오 다운로드 여부 마킹."""
    data = _read_project_file(project_id)
    if not data:
        return False
    for v in data.get("videos", []):
        if v.get("version_id") == version_id:
            v["downloaded"] = True
            _write_project_file(project_id, data)
            return True
    return False


# ═══════════════════════════════════════════════════════════════
# 추적 링크 (Phase 1-B) — 영상별 subId / deeplink / 매출 귀속
# ═══════════════════════════════════════════════════════════════

def add_tracking_record(project_id, record):
    """프로젝트에 추적 레코드 1건 추가. 동일 video_id 있으면 덮어쓰기."""
    data = _read_project_file(project_id)
    if not data:
        return False
    records = data.setdefault("tracking", [])
    vid = record.get("video_id")
    for i, r in enumerate(records):
        if r.get("video_id") == vid:
            records[i] = record
            _write_project_file(project_id, data)
            return True
    records.append(record)
    _write_project_file(project_id, data)
    return True


def list_tracking_records(project_id):
    """프로젝트의 모든 추적 레코드."""
    data = _read_project_file(project_id)
    if not data:
        return []
    return data.get("tracking", [])


def update_tracking_metrics(project_id, video_id, manual_clicks=None,
                             manual_revenue_krw=None,
                             manual_views=None, manual_likes=None,
                             manual_subscribers=None, manual_signups=None,
                             uploaded_to=None):
    """사용자가 대시보드 보고 수동 입력하는 성과 지표 갱신.

    Phase 3 일반화: revenue 외 views/likes/subscribers/signups 추가.
    """
    data = _read_project_file(project_id)
    if not data:
        return False
    for r in data.get("tracking", []):
        if r.get("video_id") == video_id:
            field_map = [
                ("manual_clicks", manual_clicks),
                ("manual_revenue_krw", manual_revenue_krw),
                ("manual_views", manual_views),
                ("manual_likes", manual_likes),
                ("manual_subscribers", manual_subscribers),
                ("manual_signups", manual_signups),
            ]
            for col, val in field_map:
                if val is not None:
                    r[col] = int(val)
            if uploaded_to is not None:
                r["uploaded_to"] = list(uploaded_to)
            _write_project_file(project_id, data)
            return True
    return False


def list_all_tracking_records():
    """모든 프로젝트의 추적 레코드 통합 (대시보드용)."""
    out = []
    for p in list_projects():
        for r in list_tracking_records(p["id"]):
            r2 = dict(r)
            r2["project_name"] = p.get("name", "")
            out.append(r2)
    return out


# ── SQLite 백엔드 위임 (활성화 시 위 JSON 함수들을 덮어씀) ──────────
if _USE_SQLITE:
    list_projects = _sqlite.list_projects
    create_project = _sqlite.create_project
    get_project = _sqlite.get_project
    update_project = _sqlite.update_project
    delete_project = _sqlite.delete_project
    add_video_version = _sqlite.add_video_version
    list_video_versions = _sqlite.list_video_versions
    get_video_version = _sqlite.get_video_version
    mark_downloaded = _sqlite.mark_downloaded
    add_tracking_record = _sqlite.add_tracking_record
    list_tracking_records = _sqlite.list_tracking_records
    update_tracking_metrics = _sqlite.update_tracking_metrics
    list_all_tracking_records = _sqlite.list_all_tracking_records


# ── JSON → SQLite 마이그레이션 ─────────────────────────────────────

def migrate_json_to_sqlite(verbose: bool = True) -> dict:
    """기존 JSON 파일들을 읽어 SQLite DB에 일괄 이전.

    - 같은 ID 프로젝트가 SQLite에 이미 있으면 건너뜀 (idempotent)
    - 추적 레코드/비디오 버전도 함께 이전
    - 실행 후에도 JSON 파일은 보존 (롤백 가능)

    Returns: {"projects": N, "videos": N, "tracking": N, "skipped": N}
    """
    import project_store_sqlite as sqlite_mod
    sqlite_mod.PROJECTS_DIR = PROJECTS_DIR  # 동기화

    stats = {"projects": 0, "videos": 0, "tracking": 0, "skipped": 0}
    if not os.path.exists(PROJECTS_DIR):
        return stats

    for name in sorted(os.listdir(PROJECTS_DIR)):
        pj = os.path.join(PROJECTS_DIR, name, "project.json")
        if not os.path.isfile(pj):
            continue
        try:
            with open(pj, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        pid = data.get("id") or name
        # 중복 체크
        if sqlite_mod.get_project(pid):
            stats["skipped"] += 1
            if verbose:
                print(f"  SKIP {pid} (이미 존재)")
            continue

        # 1) 프로젝트 자체 INSERT (시퀀스 ID 보존을 위해 SQL 직접)
        with sqlite_mod._conn() as c:
            sqlite_mod._init_schema()
            c.execute("""
                INSERT INTO projects (id, name, product_name, category, template, workspace_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                pid, data.get("name", name),
                data.get("product_name", ""), data.get("category", ""),
                data.get("template", ""), data.get("workspace_id", ""),
                data.get("created_at", time.strftime("%Y-%m-%dT%H:%M:%S")),
            ))
            stats["projects"] += 1

            # 2) 비디오 버전
            for v in data.get("videos", []):
                c.execute("""
                    INSERT INTO videos (version_id, project_id, name, hook_type,
                                         pattern_interrupt_enabled, retention_booster_enabled,
                                         tts_engine, video_path, downloaded, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    v.get("version_id"), pid, v.get("name", ""),
                    v.get("hook_type", ""),
                    int(v.get("pattern_interrupt_enabled", True)),
                    int(v.get("retention_booster_enabled", True)),
                    v.get("tts_engine", "elevenlabs"),
                    v.get("video_path", ""),
                    int(v.get("downloaded", False)),
                    v.get("created_at", time.strftime("%Y-%m-%dT%H:%M:%S")),
                ))
                stats["videos"] += 1

            # 3) 추적 레코드
            for r in data.get("tracking", []):
                c.execute("""
                    INSERT OR REPLACE INTO tracking_records (
                        project_id, video_id, sub_id, shorten_url, landing_url,
                        original_url, template, title,
                        manual_clicks, manual_revenue_krw, uploaded_to, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    pid, r.get("video_id", ""),
                    r.get("sub_id", ""), r.get("shorten_url", ""),
                    r.get("landing_url", ""), r.get("original_url", ""),
                    r.get("template", ""), r.get("title", ""),
                    int(r.get("manual_clicks", 0) or 0),
                    int(r.get("manual_revenue_krw", 0) or 0),
                    json.dumps(r.get("uploaded_to", []), ensure_ascii=False),
                    r.get("created_at", time.strftime("%Y-%m-%dT%H:%M:%S")),
                ))
                stats["tracking"] += 1

        if verbose:
            print(f"  MIGRATE {pid}: videos={len(data.get('videos', []))} "
                  f"tracking={len(data.get('tracking', []))}")
    return stats


if __name__ == "__main__":
    # CLI: python project_store.py
    print("=== JSON → SQLite 마이그레이션 ===")
    print(f"PROJECTS_DIR: {PROJECTS_DIR}")
    print(f"SQLite DB: {os.path.join(PROJECTS_DIR, 'projects.db')}\n")
    result = migrate_json_to_sqlite(verbose=True)
    print(f"\n완료: 프로젝트 {result['projects']}, 비디오 {result['videos']}, "
          f"추적 {result['tracking']} (스킵 {result['skipped']})")
    print("\n전환:")
    print('  Linux/Mac: export SHORTFORM_DB=sqlite')
    print('  Windows:   set SHORTFORM_DB=sqlite')
