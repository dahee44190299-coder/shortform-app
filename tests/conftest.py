"""pytest 공통 픽스처 — 프로젝트 루트를 sys.path에 등록.

테스트는 `python -m pytest tests/` 또는 `pytest`로 실행.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
