"""API 키 액세스 단일 진입점 (Phase 2 모듈 분리 #1).

Streamlit secrets → 환경변수 순서로 조회.
Streamlit 컨텍스트가 없어도 안전하게 동작 (try/except로 secrets 접근 가드).

테스트:
  - 환경변수만 설정한 상태에서도 동작
  - Streamlit secrets 파일이 없거나 키가 없으면 빈 문자열 반환
"""
import os


def get_api_key(name: str) -> str:
    """Secrets 또는 환경변수에서 API 키 조회. 없으면 빈 문자열."""
    try:
        import streamlit as st
        v = st.secrets.get(name, "")
        if v:
            return v
    except Exception:
        pass
    return os.getenv(name, "") or ""


def has_key(name: str) -> bool:
    """API 키 존재 여부."""
    return bool(get_api_key(name))
