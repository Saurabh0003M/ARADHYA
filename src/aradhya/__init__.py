"""Public package exports for Aradhya.

Exports are resolved lazily so importing a narrow subpackage or a single
model (such as ``src.aradhya.runtime_profile``) does not pull in the full
assistant runtime.
"""

__all__ = [
    "AradhyaAssistant",
    "AssistantPreferences",
    "AssistantResponse",
    "PlanAction",
    "PlanKind",
    "RuntimeProfile",
    "VoiceActivationProfile",
    "WakeSource",
    "build_default_preferences",
    "build_default_runtime_profile",
    "load_preferences",
    "load_runtime_profile",
]


def __getattr__(name: str):
    if name == "AradhyaAssistant":
        from src.aradhya.assistant_core import AradhyaAssistant

        return AradhyaAssistant

    if name in {
        "AssistantPreferences",
        "AssistantResponse",
        "PlanAction",
        "PlanKind",
        "WakeSource",
        "build_default_preferences",
        "load_preferences",
    }:
        from src.aradhya import assistant_models

        return getattr(assistant_models, name)

    if name in {
        "RuntimeProfile",
        "VoiceActivationProfile",
        "build_default_runtime_profile",
        "load_runtime_profile",
    }:
        from src.aradhya import runtime_profile

        return getattr(runtime_profile, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
