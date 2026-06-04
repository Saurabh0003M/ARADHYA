"""General purpose utilities."""

import json
from pathlib import Path
from typing import Any


def load_json_file(path: Path, default: Any = None) -> Any:
    """Load and parse a JSON file, returning a default value if the file is missing or invalid."""
    if default is None:
        default = {}

    if not path.is_file():
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default
