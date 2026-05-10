"""Utilities for extracting JSON from imperfect LLM responses."""

from __future__ import annotations

import json
import re
from typing import Any

from loguru import logger


class JSONExtractionError(ValueError):
    """Raised when a model response does not contain usable JSON."""


def extract_json_from_llm_response(response: str) -> dict[str, Any]:
    """Extract the first valid JSON object from an LLM response.

    The planner asks the local model for JSON-only output, but real models
    sometimes still add prose or Markdown fences. This helper keeps the parser
    strict while tolerating the most common formatting slips.
    """

    if not response or not response.strip():
        raise JSONExtractionError("The model response was empty.")

    stripped_response = response.strip()
    try:
        return json.loads(stripped_response)
    except json.JSONDecodeError:
        pass

    markdown_patterns = (
        r"```json\s*(\{.*?\})\s*```",
        r"```\s*(\{.*?\})\s*```",
        r"`(\{.*?\})`",
    )
    for pattern in markdown_patterns:
        for match in re.findall(pattern, stripped_response, re.DOTALL):
            try:
                parsed = json.loads(match.strip())
                logger.debug("Extracted JSON from Markdown-style response.")
                return parsed
            except json.JSONDecodeError:
                continue

    for candidate in _extract_json_objects(stripped_response):
        try:
            parsed = json.loads(candidate)
            logger.debug("Extracted JSON object from embedded model response.")
            return parsed
        except json.JSONDecodeError:
            continue

    cleaned_response = _clean_common_json_issues(stripped_response)
    try:
        return json.loads(cleaned_response)
    except json.JSONDecodeError as error:
        raise JSONExtractionError(
            f"Could not find valid JSON in the model response: {error}"
        ) from error


def validate_json_structure(
    data: dict[str, Any],
    *,
    required_keys: tuple[str, ...],
    allowed_keys: tuple[str, ...],
) -> None:
    """Validate that a JSON object matches the expected planner schema."""

    missing_keys = [key for key in required_keys if key not in data]
    if missing_keys:
        raise JSONExtractionError(
            "Missing required key(s): " + ", ".join(sorted(missing_keys))
        )

    unexpected_keys = [key for key in data if key not in allowed_keys]
    if unexpected_keys:
        raise JSONExtractionError(
            "Unexpected key(s) in model JSON: " + ", ".join(sorted(unexpected_keys))
        )


def _extract_json_objects(text: str) -> list[str]:
    candidates: list[str] = []
    depth = 0
    start_index: int | None = None

    for index, character in enumerate(text):
        if character == "{":
            if depth == 0:
                start_index = index
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0 and start_index is not None:
                candidates.append(text[start_index : index + 1])
                start_index = None

    return candidates


def _clean_common_json_issues(text: str) -> str:
    cleaned = re.sub(
        r"^(here(?:'s| is)? the (?:json|plan)|json|output)\s*:?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    last_brace = cleaned.rfind("}")
    if last_brace != -1:
        cleaned = cleaned[: last_brace + 1]

    if '"' not in cleaned and "'" in cleaned:
        cleaned = cleaned.replace("'", '"')

    cleaned = re.sub(r",\s*}", "}", cleaned)
    cleaned = re.sub(r",\s*]", "]", cleaned)
    return cleaned.strip()
