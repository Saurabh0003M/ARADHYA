"""User-profile tool for form assistance (P1-4).

Exposes the user's opt-in structured profile to the agent so it can fill any
multi-field web form. Read-only: it returns stored values, but actually
entering them into a form still goes through the confirmation-gated
``browser_type``. Fields the user hasn't stored are reported as missing so the
agent asks rather than inventing them.
"""

from __future__ import annotations

from src.aradhya.tools.tool_registry import tool_definition
from src.aradhya.user_profile import field_label, is_sensitive_key

# Active StructuredProfile for the current turn, set by assistant_core (mirrors
# the network-policy / vision-provider registries).
_active_profile = None


def set_active_user_profile(profile) -> None:
    """Store the current turn's StructuredProfile for get_user_profile."""
    global _active_profile
    _active_profile = profile


@tool_definition(
    name="get_user_profile",
    description=(
        "Return the user's saved profile fields (name, email, address, ...) for "
        "filling out a form. Read-only. If a form needs a field that isn't "
        "saved, ask the user for it — never invent values. Sensitive values are "
        "included so you can fill the form, but confirm before entering them."
    ),
    parameters={"type": "object", "properties": {}},
)
def get_user_profile() -> str:
    """Return saved profile fields as a readable block."""
    if _active_profile is None or _active_profile.is_empty():
        return (
            "No structured profile is saved. Ask the user for each field the "
            "form needs; do not guess. They can save fields with /profile set."
        )

    lines = ["Saved user profile fields:"]
    for key, value in sorted(_active_profile.as_dict().items()):
        tag = " (sensitive)" if is_sensitive_key(key) else ""
        lines.append(f"  - {field_label(key)} [{key}]{tag}: {value}")
    lines.append(
        "\nUse these to fill matching form fields. For any field not listed, "
        "ask the user instead of inventing a value."
    )
    return "\n".join(lines)


ALL_PROFILE_TOOLS = [get_user_profile]
