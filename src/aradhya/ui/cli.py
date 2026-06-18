"""Rich CLI rendering for the Aradhya assistant.

This module is now a thin compatibility facade. The renderers were split by
domain into ``ui/console.py`` (shared console + primitives) and the
``ui/renders/`` package (status, catalog, conversation). Everything is
re-exported here so existing ``from src.aradhya.ui.cli import ...`` imports keep
working — new code may import from the domain modules directly.
"""

from __future__ import annotations

from src.aradhya.ui.console import (
    ARADHYA_THEME,
    console,
    render_error,
    render_info,
    render_success,
    render_warning,
)
from src.aradhya.ui.renders.status import (
    render_banner,
    render_cloud_safety_assessment,
    render_daemon_start_success,
    render_federation_doctor,
    render_federation_status,
    render_health_check,
    render_model_ask_result,
    render_model_workers,
    render_skills_list,
    render_status,
    render_topology,
)
from src.aradhya.ui.renders.catalog import (
    render_api_categories,
    render_api_entries,
    render_api_entry,
    render_audit,
    render_parasite_candidates,
    render_parasite_inspect,
    render_parasite_status,
)
from src.aradhya.ui.renders.conversation import (
    VoiceStatusConfig,
    get_prompt,
    prompt_input,
    render_help,
    render_response,
    render_stream,
    render_tool_confirmation_prompt,
    render_voice_status,
)

__all__ = [
    "ARADHYA_THEME",
    "console",
    "render_info",
    "render_success",
    "render_warning",
    "render_error",
    "render_banner",
    "render_status",
    "render_topology",
    "render_federation_status",
    "render_federation_doctor",
    "render_model_workers",
    "render_cloud_safety_assessment",
    "render_model_ask_result",
    "render_daemon_start_success",
    "render_health_check",
    "render_skills_list",
    "render_api_categories",
    "render_api_entries",
    "render_api_entry",
    "render_audit",
    "render_parasite_candidates",
    "render_parasite_inspect",
    "render_parasite_status",
    "render_response",
    "render_help",
    "VoiceStatusConfig",
    "render_voice_status",
    "render_tool_confirmation_prompt",
    "get_prompt",
    "prompt_input",
    "render_stream",
]
