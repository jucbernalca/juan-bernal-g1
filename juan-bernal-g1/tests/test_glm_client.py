import pytest
from src.api.glm_client import extract_json_from_text, GLMResponseParseError


class TestJsonExtraction:
    def test_clean_json(self):
        text = '{"category": "Otro", "priority": "P3"}'
        result = extract_json_from_text(text)
        assert result["category"] == "Otro"

    def test_json_with_pretext(self):
        text = 'Aqui esta el resultado:\n{"category": "Otro", "priority": "P3"}'
        result = extract_json_from_text(text)
        assert result["category"] == "Otro"

    def test_json_in_markdown(self):
        text = '```json\n{"category": "Otro", "priority": "P3"}\n```'
        result = extract_json_from_text(text)
        assert result["category"] == "Otro"

    def test_json_in_markdown_no_label(self):
        text = '```\n{"category": "Otro", "priority": "P3"}\n```'
        result = extract_json_from_text(text)
        assert result["category"] == "Otro"

    def test_no_json_raises(self):
        with pytest.raises(GLMResponseParseError):
            extract_json_from_text("No hay JSON aqui")

    def test_nested_json(self):
        text = 'Resultado: {"a": {"b": 1}, "c": [1, 2, 3]}'
        result = extract_json_from_text(text)
        assert result["a"]["b"] == 1
        assert result["c"] == [1, 2, 3]
