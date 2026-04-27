"""eval_metrics.py 단위 테스트 — Phase 1-C LLM 호출 평가."""
import json

import pytest

import eval_metrics


@pytest.fixture
def isolated_metrics(tmp_path, monkeypatch):
    """각 테스트가 별도 임시 디렉토리를 쓰도록 격리."""
    fake_dir = tmp_path / "_metrics"
    fake_log = fake_dir / "llm_calls.jsonl"
    monkeypatch.setattr(eval_metrics, "METRICS_DIR", str(fake_dir))
    monkeypatch.setattr(eval_metrics, "LLM_LOG_PATH", str(fake_log))
    return fake_log


class TestEvaluateScript:
    def test_empty_returns_zeros(self):
        m = eval_metrics.evaluate_script("")
        assert m["char_len"] == 0
        assert m["has_hook"] is False
        assert m["has_cta"] is False

    def test_detects_hook_indicator(self):
        m = eval_metrics.evaluate_script("진짜 이거 모르면 손해? 빨리 와요")
        assert m["has_hook"] is True
        assert m["has_question"] is True

    def test_detects_cta(self):
        m = eval_metrics.evaluate_script("이 제품 쩔어요. 설명란 링크 확인하세요!")
        assert m["has_cta"] is True

    def test_counts_sentences(self):
        m = eval_metrics.evaluate_script("문장1. 문장2! 문장3?")
        assert m["sentence_count"] == 3

    def test_char_len(self):
        text = "안녕하세요"
        assert eval_metrics.evaluate_script(text)["char_len"] == 5


class TestLogLlmCall:
    def test_log_creates_file_and_appends(self, isolated_metrics):
        log_path = isolated_metrics
        ok = eval_metrics.log_llm_call(
            prompt_type="test", model="claude-x",
            response="진짜? 설명란 링크",
            prompt_chars=50, latency_ms=300,
        )
        assert ok is True
        assert log_path.exists()
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        rec = json.loads(lines[0])
        assert rec["prompt_type"] == "test"
        assert rec["model"] == "claude-x"
        assert rec["latency_ms"] == 300
        assert "metrics" in rec

    def test_multiple_appends(self, isolated_metrics):
        for i in range(3):
            eval_metrics.log_llm_call(
                prompt_type="t", model="m", response=f"text {i}",
            )
        lines = isolated_metrics.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 3

    def test_extra_field_persisted(self, isolated_metrics):
        eval_metrics.log_llm_call(
            prompt_type="t", model="m", response="x",
            extra={"category": "food", "case_id": "ev01"},
        )
        rec = json.loads(isolated_metrics.read_text(encoding="utf-8").strip())
        assert rec["extra"]["category"] == "food"


class TestComputeStats:
    def test_empty_returns_zero_count(self, isolated_metrics):
        stats = eval_metrics.compute_stats(days=7)
        assert stats["count"] == 0

    def test_aggregates_correctly(self, isolated_metrics):
        # 3건 누적
        for resp in ["짧음", "조금 더 긴 문장입니다 설명란", "?진짜 진짜 긴 문장 설명란 링크 클릭"]:
            eval_metrics.log_llm_call(prompt_type="t", model="m", response=resp,
                                       latency_ms=100)
        stats = eval_metrics.compute_stats(days=7)
        assert stats["count"] == 3
        assert stats["by_prompt_type"]["t"] == 3
        # 평균 글자 수 > 0
        assert stats["metrics"]["char_len"]["mean"] > 0
        # CTA 포함률: "설명란"이 들어간 건 2건 → 66.7%
        assert stats["metrics"]["has_cta_pct"] > 0

    def test_filter_by_prompt_type(self, isolated_metrics):
        eval_metrics.log_llm_call(prompt_type="a", model="m", response="x")
        eval_metrics.log_llm_call(prompt_type="b", model="m", response="y")
        eval_metrics.log_llm_call(prompt_type="a", model="m", response="z")
        stats_a = eval_metrics.compute_stats(prompt_type="a", days=7)
        stats_b = eval_metrics.compute_stats(prompt_type="b", days=7)
        assert stats_a["count"] == 2
        assert stats_b["count"] == 1
