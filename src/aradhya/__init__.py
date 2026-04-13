"""Public package exports for Aradhya."""

from __future__ import annotations

from src.aradhya.assistant_core import AradhyaAssistant
from src.aradhya.assistant_models import (
    AssistantPreferences,
    AssistantResponse,
    PlanAction,
    PlanKind,
    ShellStateSnapshot,
    WakeSource,
    build_default_preferences,
    load_preferences,
)
from src.aradhya.runtime_profile import (
    RuntimeProfile,
    VoiceActivationProfile,
    build_default_runtime_profile,
    load_runtime_profile,
)

__all__ = [
    "AradhyaAssistant",
    "AssistantPreferences",
    "AssistantResponse",
    "FloatingShellController",
    "PlanAction",
    "PlanKind",
    "RuntimeProfile",
    "ShellStateSnapshot",
    "VoiceActivationProfile",
    "WakeSource",
    "build_default_preferences",
    "build_default_runtime_profile",
    "load_preferences",
    "load_runtime_profile",
]


def __getattr__(name: str):
    if name == "FloatingShellController":
        from src.aradhya.floating_shell import FloatingShellController

        return FloatingShellController
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
