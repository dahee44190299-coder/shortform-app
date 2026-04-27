"""SQLite 백엔드 — project_store.py와 동일한 Public API.

전환 방법:
  환경변수 SHORTFORM_DB=sqlite 설정 후 앱 재시작.
  기존 JSON 데이터는 migrate.py로 일괄 이전.

Why SQLite:
  - 멀티유저 동시 접근 (JSON 파일은 race condition)
  - SQL 쿼리로 카테고리별/기간별 집계 가능
  - 트랜잭션 보장 (추적 레코드 매출 갱신 시 부분 실패 방지)
  - Phase 2 데이터 해자(영상 1만건 → AI 추천)의 필수 인프라

설계:
  - 동일한 함수 시그니처 유지 → 기존 호출자 변경 불필요
  - PROJECTS_DIR을 환경변수로 받아 DB 파일 위치 결정
  - 스키마는 idempotent CREATE IF NOT EXISTS
"""
import json
import os
import sqlite3
import time
from contextlib import contextmanager


PROJECTS_DIR = "shortform_projects"
_DB_NAME = "projects.db"


def _db_path() -> str:
    return os.path.join(PROJECTS_DIR, _DB_NAME)


def _ensure_dir():
    os.makedirs(PROJECTS_DIR, exist_ok=True)


SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    product_name TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    template TEXT NOT NULL DEFAULT '',
    workspace_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS videos (
    version_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL DEFAULT '',
    hook_type TEXT NOT NULL DEFAULT '',
    pattern_interrupt_enabled INTEGER NOT NULL DEFAULT 1,
    retention_booster_enabled INTEGER NOT NULL DEFAULT 1,
    tts_engine TEXT NOT NULL DEFAULT 'elevenlabs',
    video_path TEXT NOT NULL DEFAULT '',
    downloaded INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tracking_records (
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    video_id TEXT NOT NULL,
    sub_id TEXT NOT NULL DEFAULT '',
    shorten_url TEXT NOT NULL DEFAULT '',
    landing_url TEXT NOT NULL DEFAULT '',
    original_url TEXT NOT NULL DEFAULT '',
    template TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    manual_clicks INTEGER NOT NULL DEFAULT 0,
    manual_revenue_krw INTEGER NOT NULL DEFAULT 0,
    uploaded_to TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    PRIMARY KEY (project_id, video_id)
);

CREATE INDEX IF NOT EXISTS idx_videos_project ON videos(project_id);
CREATE INDEX IF NOT EXISTS idx_tracking_project ON tracking_records(project_id);
"""


@contextmanager
def _conn():
    _ensure_dir()
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _init_schema():
    """스키마 보장. 호출 시점마다 호출해도 안전 (IF NOT EXISTS)."""
    with _conn() as c:
        c.executescript(SCHEMA)


# ═══════════════════════════════════════════════════════════════
# Public API — project_store.py와 동일 시그니처
# ═══════════════════════════════════════════════════════════════

def list_projects() -> list:
    _init_schema()
    with _conn() as c:
        rows = c.execute("""
            SELECT p.id, p.name, p.created_at, p.template,
                   (SELECT COUNT(*) FROM videos v WHERE v.project_id = p.id) AS video_count
            FROM projects p
            ORDER BY p.id ASC
        """).fetchall()
        return [dict(r) for r in rows]


def create_project(name: str, product_name: str = "", category: str = "",
                   template: str = "") -> str:
    _init_schema()
    project_id = f"prj_{int(time.time() * 1000)}"
    with _conn() as c:
        c.execute("""
            INSERT INTO projects (id, name, product_name, category, template, workspace_id, created_at)
            VALUES (?, ?, ?, ?, ?, '', ?)
        """, (project_id, name, product_name, category, template,
              time.strftime("%Y-%m-%dT%H:%M:%S")))
    return project_id


def get_project(project_id: str):
    _init_schema()
    with _conn() as c:
        row = c.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not row:
            return None
        data = dict(row)
        videos = c.execute("""
            SELECT version_id, name, hook_type,
                   pattern_interrupt_enabled, retention_booster_enabled,
                   tts_engine, video_path, downloaded, created_at
            FROM videos WHERE project_id = ? ORDER BY version_id ASC
        """, (project_id,)).fetchall()
        data["videos"] = [
            {
                **dict(v),
                "pattern_interrupt_enabled": bool(v["pattern_interrupt_enabled"]),
                "retention_booster_enabled": bool(v["retention_booster_enabled"]),
                "downloaded": bool(v["downloaded"]),
            }
            for v in videos
        ]
        return data


def update_project(project_id: str, **kwargs) -> bool:
    allowed = {"name", "product_name", "category", "template", "workspace_id"}
    fields = [k for k in kwargs if k in allowed]
    if not fields:
        return False
    _init_schema()
    with _conn() as c:
        cur = c.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,))
        if not cur.fetchone():
            return False
        sets = ", ".join(f"{f} = ?" for f in fields)
        values = [kwargs[f] for f in fields] + [project_id]
        c.execute(f"UPDATE projects SET {sets} WHERE id = ?", values)
        return True


def delete_project(project_id: str) -> bool:
    _init_schema()
    with _conn() as c:
        cur = c.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        return cur.rowcount > 0


def add_video_version(project_id: str, name: str, hook_type: str = "",
                      pattern_interrupt: bool = True, retention_booster: bool = True,
                      tts_engine: str = "elevenlabs", video_path: str = ""):
    _init_schema()
    version_id = f"v_{int(time.time() * 1000)}"
    with _conn() as c:
        if not c.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone():
            return None
        c.execute("""
            INSERT INTO videos (version_id, project_id, name, hook_type,
                                 pattern_interrupt_enabled, retention_booster_enabled,
                                 tts_engine, video_path, downloaded, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
        """, (version_id, project_id, name, hook_type,
              int(pattern_interrupt), int(retention_booster),
              tts_engine, video_path,
              time.strftime("%Y-%m-%dT%H:%M:%S")))
    return version_id


def list_video_versions(project_id: str) -> list:
    _init_schema()
    with _conn() as c:
        rows = c.execute("""
            SELECT version_id, name, hook_type,
                   pattern_interrupt_enabled, retention_booster_enabled,
                   tts_engine, video_path, downloaded, created_at
            FROM videos WHERE project_id = ? ORDER BY version_id ASC
        """, (project_id,)).fetchall()
        return [
            {
                **dict(r),
                "pattern_interrupt_enabled": bool(r["pattern_interrupt_enabled"]),
                "retention_booster_enabled": bool(r["retention_booster_enabled"]),
                "downloaded": bool(r["downloaded"]),
            }
            for r in rows
        ]


def get_video_version(project_id: str, version_id: str):
    for v in list_video_versions(project_id):
        if v.get("version_id") == version_id:
            return v
    return None


def mark_downloaded(project_id: str, version_id: str) -> bool:
    _init_schema()
    with _conn() as c:
        cur = c.execute("""
            UPDATE videos SET downloaded = 1
            WHERE project_id = ? AND version_id = ?
        """, (project_id, version_id))
        return cur.rowcount > 0


# ── 추적 레코드 ────────────────────────────────────────────────

def add_tracking_record(project_id: str, record: dict) -> bool:
    _init_schema()
    with _conn() as c:
        if not c.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone():
            return False
        c.execute("""
            INSERT OR REPLACE INTO tracking_records (
                project_id, video_id, sub_id, shorten_url, landing_url,
                original_url, template, title,
                manual_clicks, manual_revenue_krw, uploaded_to, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            project_id,
            record.get("video_id", ""),
            record.get("sub_id", ""),
            record.get("shorten_url", ""),
            record.get("landing_url", ""),
            record.get("original_url", ""),
            record.get("template", ""),
            record.get("title", ""),
            int(record.get("manual_clicks", 0) or 0),
            int(record.get("manual_revenue_krw", 0) or 0),
            json.dumps(record.get("uploaded_to", []), ensure_ascii=False),
            record.get("created_at", time.strftime("%Y-%m-%dT%H:%M:%S")),
        ))
    return True


def list_tracking_records(project_id: str) -> list:
    _init_schema()
    with _conn() as c:
        rows = c.execute("""
            SELECT video_id, project_id, sub_id, shorten_url, landing_url,
                   original_url, template, title,
                   manual_clicks, manual_revenue_krw, uploaded_to, created_at
            FROM tracking_records WHERE project_id = ?
            ORDER BY created_at ASC
        """, (project_id,)).fetchall()
        return [_row_to_tracking(r) for r in rows]


def update_tracking_metrics(project_id: str, video_id: str,
                             manual_clicks=None, manual_revenue_krw=None,
                             uploaded_to=None) -> bool:
    _init_schema()
    sets, values = [], []
    if manual_clicks is not None:
        sets.append("manual_clicks = ?")
        values.append(int(manual_clicks))
    if manual_revenue_krw is not None:
        sets.append("manual_revenue_krw = ?")
        values.append(int(manual_revenue_krw))
    if uploaded_to is not None:
        sets.append("uploaded_to = ?")
        values.append(json.dumps(list(uploaded_to), ensure_ascii=False))
    if not sets:
        return False
    values.extend([project_id, video_id])
    with _conn() as c:
        cur = c.execute(
            f"UPDATE tracking_records SET {', '.join(sets)} "
            f"WHERE project_id = ? AND video_id = ?",
            values,
        )
        return cur.rowcount > 0


def list_all_tracking_records() -> list:
    _init_schema()
    with _conn() as c:
        rows = c.execute("""
            SELECT t.*, p.name AS project_name
            FROM tracking_records t
            JOIN projects p ON p.id = t.project_id
            ORDER BY t.created_at ASC
        """).fetchall()
        return [_row_to_tracking(r) for r in rows]


def _row_to_tracking(row) -> dict:
    d = dict(row)
    try:
        d["uploaded_to"] = json.loads(d.get("uploaded_to") or "[]")
    except (json.JSONDecodeError, TypeError):
        d["uploaded_to"] = []
    return d
