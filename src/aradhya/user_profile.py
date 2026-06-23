"""Structured, opt-in user profile for general form assistance (P1-4).

Freeform ``rules.md`` / ``notes.md`` capture preferences and personality; this
store captures the discrete, reusable fields a *form* asks for (name, email,
city, ...) so the agent can help fill any multi-field web form rather than one
hardcoded portal.

Privacy stance: nothing is stored unless the user opts in (via ``/profile set``).
Fields flagged ``sensitive`` (phone, address, DOB, ...) are never injected into
the prompt — the agent must fetch them deliberately via the ``get_user_profile``
tool and the user still confirms each ``browser_type`` before anything is
entered into a form.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProfileField:
    """A known profile field and whether it is sensitive."""

    key: str
    label: str
    sensitive: bool = False


# Common form fields. Custom keys outside this schema are allowed too (forms
# vary); they are treated as non-sensitive with the key as the label.
PROFILE_SCHEMA: tuple[ProfileField, ...] = (
    ProfileField("full_name", "Full name"),
    ProfileField("preferred_name", "Preferred name"),
    ProfileField("email", "Email address"),
    ProfileField("phone", "Phone number", sensitive=True),
    ProfileField("address_line1", "Address line 1", sensitive=True),
    ProfileField("address_line2", "Address line 2", sensitive=True),
    ProfileField("city", "City"),
    ProfileField("state_region", "State / region"),
    ProfileField("postal_code", "Postal code", sensitive=True),
    ProfileField("country", "Country"),
    ProfileField("date_of_birth", "Date of birth", sensitive=True),
    ProfileField("occupation", "Occupation"),
    ProfileField("organization", "Organization / employer"),
    ProfileField("website", "Website"),
)

_SCHEMA_BY_KEY = {field.key: field for field in PROFILE_SCHEMA}

PROFILE_FILENAME = "structured_profile.json"


def profile_path(project_root: Path) -> Path:
    return project_root / "core" / "memory" / "user_context" / PROFILE_FILENAME


def field_label(key: str) -> str:
    field = _SCHEMA_BY_KEY.get(key)
    return field.label if field else key


def is_sensitive_key(key: str) -> bool:
    field = _SCHEMA_BY_KEY.get(key)
    return field.sensitive if field else False


class StructuredProfile:
    """Load/save and query a user's opt-in structured profile."""

    def __init__(self, path: Path, data: dict[str, str] | None = None) -> None:
        self.path = path
        self._data: dict[str, str] = {k: str(v) for k, v in (data or {}).items()}

    @classmethod
    def load(cls, path: Path) -> "StructuredProfile":
        """Load from disk, tolerating a missing or corrupt file."""
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls(path, {})
        if not isinstance(raw, dict):
            return cls(path, {})
        # Keep only string values; ignore anything malformed.
        data = {str(k): str(v) for k, v in raw.items() if isinstance(v, (str, int, float))}
        return cls(path, data)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def set(self, key: str, value: str) -> None:
        clean_key = key.strip().lower().replace(" ", "_")
        if not clean_key:
            raise ValueError("Profile field name cannot be empty.")
        self._data[clean_key] = value.strip()

    def get(self, key: str) -> str | None:
        return self._data.get(key.strip().lower().replace(" ", "_"))

    def clear(self, key: str) -> bool:
        clean_key = key.strip().lower().replace(" ", "_")
        if clean_key in self._data:
            del self._data[clean_key]
            return True
        return False

    def as_dict(self) -> dict[str, str]:
        return dict(self._data)

    def available_keys(self) -> list[str]:
        return sorted(self._data.keys())

    def non_sensitive_keys(self) -> list[str]:
        return sorted(k for k in self._data if not is_sensitive_key(k))

    def is_empty(self) -> bool:
        return not self._data
