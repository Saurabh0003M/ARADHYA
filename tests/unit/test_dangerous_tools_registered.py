"""Guards P0-2: every name in AgentLoop.DANGEROUS_TOOLS must map to a real,
registered tool handler. This stops the safety set from drifting back into
listing phantom tools (delete_file / move_file / browser_submit were listed
as dangerous but had no implementation)."""

from __future__ import annotations

from src.aradhya.agent_loop import AgentLoop
from src.aradhya.tools.browser_tools import ALL_BROWSER_TOOLS
from src.aradhya.tools.file_tools import ALL_FILE_TOOLS
from src.aradhya.tools.power_tools import ALL_POWER_TOOLS
from src.aradhya.tools.scheduler_tool import ALL_SCHEDULER_TOOLS
from src.aradhya.tools.session_tools import ALL_SESSION_TOOLS
from src.aradhya.tools.shell_tools import ALL_SHELL_TOOLS
from src.aradhya.tools.system_tools import ALL_SYSTEM_TOOLS
from src.aradhya.tools.vision_tools import ALL_VISION_TOOLS
from src.aradhya.tools.web_tools import ALL_WEB_TOOLS


def _all_registered_tool_names() -> set[str]:
    names: set[str] = set()
    for collection in (
        ALL_FILE_TOOLS,
        ALL_SHELL_TOOLS,
        ALL_SYSTEM_TOOLS,
        ALL_SESSION_TOOLS,
        ALL_WEB_TOOLS,
        ALL_POWER_TOOLS,
        ALL_BROWSER_TOOLS,
        ALL_VISION_TOOLS,
        ALL_SCHEDULER_TOOLS,
    ):
        for func in collection:
            names.add(func._tool_def.name)
    return names


def test_every_dangerous_tool_has_a_handler():
    registered = _all_registered_tool_names()
    missing = sorted(name for name in AgentLoop.DANGEROUS_TOOLS if name not in registered)
    assert not missing, f"DANGEROUS_TOOLS lists tools with no handler: {missing}"


def test_formerly_phantom_tools_now_exist():
    registered = _all_registered_tool_names()
    for name in ("delete_file", "move_file", "browser_submit"):
        assert name in registered, f"{name} should be registered now"
