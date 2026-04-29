"""Runtime policy checks for model-callable tools."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ToolPolicyDecision:
    """Decision returned before a tool call is executed."""

    allowed: bool
    message: str = ""
    requires_confirmation: bool = False


@dataclass(frozen=True)
class ToolRuntimePolicy:
    """Bounds tool execution for the model-driven agent loop."""

    allowed_roots: tuple[Path, ...]
    live_execution_enabled: bool = False
    mutation_granted: bool = False

    _MUTATING_TOOLS = {
        "write_file",
        "run_command",
        "open_path",
        "open_url",
        "clipboard_write",
        "save_note",
    }
    _PATH_ARGUMENTS = {
        "read_file": ("path",),
        "list_directory": ("path",),
        "search_files": ("path",),
        "write_file": ("path",),
        "open_path": ("path",),
    }

    def check(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        requires_confirmation: bool = False,
    ) -> ToolPolicyDecision:
        """Return whether a tool may execute under the current grant."""

        path_decision = self._check_path_arguments(tool_name, arguments)
        if not path_decision.allowed:
            return path_decision

        if tool_name == "run_command":
            cwd_decision = self._check_cwd(arguments)
            if not cwd_decision.allowed:
                return cwd_decision

        if requires_confirmation or tool_name in self._MUTATING_TOOLS:
            if not self.mutation_granted:
                return ToolPolicyDecision(
                    allowed=False,
                    message=(
                        f"Tool '{tool_name}' requires a confirmed task grant before "
                        "it can change the machine."
                    ),
                    requires_confirmation=True,
                )
            if not self.live_execution_enabled:
                return ToolPolicyDecision(
                    allowed=False,
                    message=(
                        f"Tool '{tool_name}' was blocked because allow_live_execution "
                        "is false in preferences."
                    ),
                    requires_confirmation=True,
                )

        return ToolPolicyDecision(allowed=True)

    def _check_path_arguments(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ToolPolicyDecision:
        for argument_name in self._PATH_ARGUMENTS.get(tool_name, ()):
            raw_path = arguments.get(argument_name)
            if not raw_path:
                continue
            target = Path(str(raw_path)).expanduser().resolve()
            if not self._is_inside_allowed_roots(target):
                return ToolPolicyDecision(
                    allowed=False,
                    message=(
                        f"Tool '{tool_name}' path is outside configured roots: "
                        f"{target}"
                    ),
                )
        return ToolPolicyDecision(allowed=True)

    def _check_cwd(self, arguments: dict[str, Any]) -> ToolPolicyDecision:
        raw_cwd = arguments.get("cwd", ".")
        cwd = Path(str(raw_cwd)).expanduser().resolve()
        if self._is_inside_allowed_roots(cwd):
            return ToolPolicyDecision(allowed=True)
        return ToolPolicyDecision(
            allowed=False,
            message=f"Tool 'run_command' cwd is outside configured roots: {cwd}",
        )

    def _is_inside_allowed_roots(self, target: Path) -> bool:
        for root in self.allowed_roots:
            resolved_root = root.expanduser().resolve()
            try:
                target.relative_to(resolved_root)
                return True
            except ValueError:
                continue
        return False
