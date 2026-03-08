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
