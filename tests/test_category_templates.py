"""category_templates.py 단위 테스트 — 카테고리 추론 + 템플릿 가이드."""
import json
from pathlib import Path

import category_templates


class TestInferCategory:
    def test_empty_input_returns_general(self):
        assert category_templates.infer_category("") == "general"
        assert category_templates.infer_category("", "") == "general"

    def test_digital_keywords(self):
        assert category_templates.infer_category("아이폰 15 충전기") == "digital"
        assert category_templates.infer_category("LG 그램 노트북 17인치") == "digital"

    def test_beauty_keywords(self):
        assert category_templates.infer_category("닥터자르트 시카페어 토너") == "beauty"
        assert category_templates.infer_category("시트 마스크 10매") == "beauty"

    def test_food_keywords(self):
        assert category_templates.infer_category("농심 신라면 멀티팩") == "food"
        assert category_templates.infer_category("닭가슴살 다이어트") == "food"

    def test_unknown_falls_back_to_general(self):
        assert category_templates.infer_category("zzzfoobar") == "general"

    def test_eval_dataset_100_pct(self):
        """전체 50 케이스 데이터셋 — 정확도가 80% 이하로 떨어지면 회귀."""
        path = Path(__file__).resolve().parent.parent / "eval_data" / "eval_cases.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        cases = data["cases"]
        correct = sum(
            1 for c in cases
            if category_templates.infer_category(c["product_title"]) == c["expected_category"]
        )
        accuracy = correct / len(cases)
        assert accuracy >= 0.80, f"정확도 회귀: {accuracy*100:.1f}% (50 케이스)"


class TestGetTemplate:
    def test_known_category_returns_profile(self):
        prof = category_templates.get_template("beauty")
        assert "label" in prof
        assert "hook_pattern" in prof
        assert "structure" in prof
        assert "cta" in prof
        assert "do_not" in prof

    def test_unknown_category_returns_general(self):
        prof = category_templates.get_template("nonexistent_xyz")
        assert prof["label"] == category_templates.CATEGORY_PROFILES["general"]["label"]


class TestListCategories:
    def test_returns_id_label_pairs(self):
        cats = category_templates.list_categories()
        assert len(cats) >= 7  # 7 카테고리 + general
        for cid, label in cats:
            assert isinstance(cid, str)
            assert isinstance(label, str)


class TestFormatCategoryHint:
    def test_contains_required_sections(self):
        hint = category_templates.format_category_hint("food")
        assert "카테고리:" in hint
        assert "Hook 패턴:" in hint
        assert "영상 구조:" in hint
        assert "CTA 권장:" in hint
        assert "금지사항:" in hint

    def test_unknown_category_uses_general(self):
        hint = category_templates.format_category_hint("xyz_nonexistent")
        assert "기타" in hint or "일반" in hint
