from __future__ import annotations

import pytest

from src.aradhya.json_extractor import (
    JSONExtractionError,
    extract_json_from_llm_response,
    validate_json_structure,
)


def test_extract_json_from_markdown_code_block():
    response = """
    Here is the plan:
    ```json
    {"intent": "OPEN_PATH", "confidence": 0.9, "reasoning": "clear", "target": "Notes", "enabled": null}
    ```
    """

    result = extract_json_from_llm_response(response)

    assert result["intent"] == "OPEN_PATH"
    assert result["target"] == "Notes"


def test_extract_json_cleans_trailing_commas():
    response = """{"intent": "UNKNOWN", "confidence": 0.1, "reasoning": "bad", "target": null, "enabled": null,}"""

    result = extract_json_from_llm_response(response)

    assert result["intent"] == "UNKNOWN"


def test_validate_json_structure_rejects_unexpected_keys():
    with pytest.raises(JSONExtractionError):
        validate_json_structure(
            {"intent": "OPEN_PATH", "confidence": 0.9, "reasoning": "x", "target": "Notes", "enabled": None, "command": "rm -rf /"},
            required_keys=("intent", "confidence", "reasoning", "target", "enabled"),
            allowed_keys=("intent", "confidence", "reasoning", "target", "enabled"),
        )
