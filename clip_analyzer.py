"""
자동 클립 분석·분할 모듈 (FFmpeg 기반)

사용:
    from clip_analyzer import analyze_scenes, split_clips

    timestamps = analyze_scenes("input.mp4")
    clips = split_clips("input.mp4", timestamps)
"""

import subprocess
import json
import os
import re
from pathlib import Path
import tempfile

TMPDIR = tempfile.gettempdir()


def _ensure_clip_dir():
    d = Path(TMPDIR) / "auto_clips"
    d.mkdir(exist_ok=True)
    return d


def analyze_scenes(video_path, threshold=0.3, min_dur=1.0, max_dur=10.0):
    """
    FFmpeg scene detection 기반 장면 전환 지점 추출.

    Args:
        video_path: 분석할 영상 경로
        threshold: 장면 변화 감도 (0.0~1.0, 낮을수록 민감)
        min_dur: 최소 클립 길이 (초)
        max_dur: 최대 클립 길이 (초)

    Returns:
        list of float: 장면 전환 타임스탬프 목록 (초 단위)
        빈 리스트면 장면 감지 실패
    """
    if not os.path.exists(video_path):
        return []

    # 영상 전체 길이 구하기
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "json", str(video_path)],
            capture_output=True, text=True, timeout=15
        )
        total_dur = float(json.loads(probe.stdout)["format"]["duration"])
    except Exception:
        return []

    if total_dur <= min_dur:
        return []

    # FFmpeg scene detection
    try:
        result = subprocess.run(
            ["ffmpeg", "-i", str(video_path),
             "-filter:v", f"select='gt(scene,{threshold})',showinfo",
             "-f", "null", "-"],
            capture_output=True, text=True, timeout=120
        )
        stderr = result.stderr
    except subprocess.TimeoutExpired:
        return []
    except Exception:
        return []

    # showinfo 출력에서 pts_time 추출
    raw_timestamps = []
    for line in stderr.split("\n"):
        if "pts_time:" in line:
            match = re.search(r"pts_time:\s*([\d.]+)", line)
            if match:
                t = float(match.group(1))
                if 0 < t < total_dur:
                    raw_timestamps.append(t)

    if not raw_timestamps:
        # 장면 감지 실패 시 균등 분할 fallback
        return _uniform_split(total_dur, min_dur, max_dur)

    # 타임스탬프 정제: min_dur / max_dur 조건 적용
    timestamps = _refine_timestamps(raw_timestamps, total_dur, min_dur, max_dur)
    return timestamps


def _uniform_split(total_dur, min_dur, max_dur):
    """장면 감지 실패 시 균등 분할."""
    interval = min(max_dur, max(min_dur, total_dur / max(1, int(total_dur / max_dur))))
    ts = []
    t = interval
    while t < total_dur - min_dur:
        ts.append(round(t, 2))
        t += interval
    return ts


def _refine_timestamps(raw_ts, total_dur, min_dur, max_dur):
    """타임스탬프 정제: 너무 짧은 구간 병합, 너무 긴 구간 분할."""
    # 정렬 + 중복 제거
    ts = sorted(set(raw_ts))

    # 1단계: 너무 짧은 구간 병합 (min_dur 미만)
    refined = []
    for t in ts:
        if not refined:
            if t >= min_dur:
                refined.append(t)
        else:
            if t - refined[-1] >= min_dur:
                refined.append(t)

    # 2단계: 너무 긴 구간 분할 (max_dur 초과)
    final = []
    prev = 0.0
    for t in refined:
        gap = t - prev
        if gap > max_dur:
            # 긴 구간을 max_dur 간격으로 분할
            split_t = prev + max_dur
            while split_t < t - min_dur:
                final.append(round(split_t, 2))
                split_t += max_dur
        final.append(round(t, 2))
        prev = t

    # 마지막 구간도 max_dur 초과 시 분할
    if total_dur - prev > max_dur:
        split_t = prev + max_dur
        while split_t < total_dur - min_dur:
            final.append(round(split_t, 2))
            split_t += max_dur

    return final


def split_clips(video_path, timestamps, output_dir=None, min_dur=1.0):
    """
    타임스탬프 기준으로 영상을 클립으로 분할.

    Args:
        video_path: 원본 영상 경로
        timestamps: 분할 지점 리스트 (초 단위)
        output_dir: 출력 디렉토리 (None이면 자동)
        min_dur: 최소 클립 길이 (초)

    Returns:
        list of dict: [{"name", "path", "duration", "dur_sec", "source"}, ...]
        실패 시 빈 리스트
    """
    if not os.path.exists(video_path):
        return []

    out_dir = Path(output_dir) if output_dir else _ensure_clip_dir()
    out_dir.mkdir(exist_ok=True)

    # 전체 길이
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "json", str(video_path)],
            capture_output=True, text=True, timeout=15
        )
        total_dur = float(json.loads(probe.stdout)["format"]["duration"])
    except Exception:
        return []

    # 구간 목록 생성: [0, ts1, ts2, ..., total_dur]
    boundaries = [0.0] + sorted(timestamps) + [total_dur]
    clips = []
    base_name = Path(video_path).stem

    for i in range(len(boundaries) - 1):
        start = boundaries[i]
        end = boundaries[i + 1]
        dur = end - start

        if dur < min_dur:
            continue

        clip_name = f"{base_name}_clip{i+1:02d}.mp4"
        clip_path = out_dir / clip_name

        try:
            r = subprocess.run([
                "ffmpeg", "-y",
                "-ss", f"{start:.2f}",
                "-i", str(video_path),
                "-t", f"{dur:.2f}",
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac", "-b:a", "128k",
                str(clip_path)
            ], capture_output=True, text=True, timeout=60)

            if r.returncode == 0 and clip_path.exists() and clip_path.stat().st_size > 1000:
                actual_dur = dur
                # 실제 길이 확인
                try:
                    p2 = subprocess.run(
                        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                         "-of", "json", str(clip_path)],
                        capture_output=True, text=True, timeout=10
                    )
                    actual_dur = float(json.loads(p2.stdout)["format"]["duration"])
                except Exception:
                    pass

                dur_str = f"{int(actual_dur//60)}:{int(actual_dur%60):02d}"
                clips.append({
                    "name": clip_name,
                    "path": str(clip_path),
                    "duration": dur_str,
                    "dur_sec": round(actual_dur, 1),
                    "source": "auto_split",
                })
        except subprocess.TimeoutExpired:
            continue
        except Exception:
            continue

    return clips
