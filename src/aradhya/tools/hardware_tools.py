"""Hardware inspection tool (P1-6).

Exposes the detected hardware profile and reality-grounded local-model
recommendations to the agent, so "what can I run on this machine?" is answered
from real CPU/GPU/RAM rather than a static guess.
"""

from __future__ import annotations

from src.aradhya.model_setup import recommend_for_profile
from src.aradhya.tools.tool_registry import tool_definition
from src.aradhya.utils.hardware_profile import detect_hardware_profile


@tool_definition(
    name="analyze_hardware",
    description=(
        "Detect this machine's CPU, GPU, VRAM, and RAM, and report which local "
        "models it can realistically run (and when to use gated cloud instead). "
        "Read-only. Use for 'what can I run on this machine?' questions."
    ),
    parameters={"type": "object", "properties": {}},
)
def analyze_hardware() -> str:
    """Return a hardware summary plus feasible local-model recommendations."""
    profile = detect_hardware_profile()
    recommendation = recommend_for_profile(profile)
    return (
        f"Hardware:\n  {profile.summary}\n\n"
        f"{recommendation.format_for_user()}"
    )


ALL_HARDWARE_TOOLS = [analyze_hardware]
