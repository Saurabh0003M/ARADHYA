"""Runtime policy checks for model-callable tools.

Implements a Codex-inspired read/write permission split.  Each path root
can be designated as ``read`` or ``write`` access.  The legacy
``allowed_roots`` parameter is preserved for backward compatibility and
treated as granting both read and write access.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
    """Bounds tool execution for the model-driven agent loop.

    Parameters
    ----------
    allowed_roots
        Legacy field — paths with both read and write access.
    read_roots
        Paths with read-only access.  Defaults to ``allowed_roots``.
    write_roots
        Paths with write access.  Defaults to ``allowed_roots``.
    live_execution_enabled
        Whether mutating tools may actually execute.
    mutation_granted
        Whether the user has confirmed a task grant.
    """

    allowed_roots: tuple[Path, ...] = ()
    read_roots: tuple[Path, ...] = ()
    write_roots: tuple[Path, ...] = ()
    live_execution_enabled: bool = False
    mutation_granted: bool = False
    network_allowed: bool = True
    """Gap E: When False, web_fetch and web_search are denied.

    Mirrors Codex's ``sandbox_policy.network_access: false`` — prevents
    prompt-injection via malicious web content that triggers tool chains.
    Set to False for high-security / air-gapped sessions.
    """

    def __post_init__(self) -> None:
        # Backward compatibility: if only allowed_roots is set, populate
        # read_roots and write_roots from it.
        if self.allowed_roots and not self.read_roots:
            object.__setattr__(self, "read_roots", self.allowed_roots)
        if self.allowed_roots and not self.write_roots:
            object.__setattr__(self, "write_roots", self.allowed_roots)

    _MUTATING_TOOLS = {
        "write_file",
        "run_command",
        "open_path",
        "open_url",
        "clipboard_write",
        "save_note",
    }

    _READ_TOOLS = {
        "read_file",
        "list_directory",
        "search_files",
    }

    _WRITE_TOOLS = {
        "write_file",
        "open_path",
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

    def check_network_access(self, tool_name: str) -> ToolPolicyDecision:
        """Return whether a network tool may execute (Gap E).

        Called by ``web_fetch`` and ``web_search`` before making outbound
        HTTP requests.  When ``network_allowed`` is False, the tool returns
        a policy-denial result instead of fetching the URL — preventing
        prompt-injection attacks via crafted web content.
        """
        if not self.network_allowed:
            return ToolPolicyDecision(
                allowed=False,
                message=(
                    f"Tool '{tool_name}' blocked — network access is disabled "
                    "in the current session policy (network_allowed=False). "
                    "Enable it in preferences or ask the user to allow network access."
                ),
            )
        return ToolPolicyDecision(allowed=True)

    def to_permission_profile(self) -> dict[str, Any]:
        """Serialize the permission matrix for turn_context injection.

        Returns a dict matching Codex's ``permission_profile`` schema.
        """
        return {
            "read_roots": [str(r) for r in self._effective_read_roots()],
            "write_roots": [str(r) for r in self._effective_write_roots()],
            "live_execution": self.live_execution_enabled,
            "mutation_granted": self.mutation_granted,
            "network": "allowed" if self.network_allowed else "restricted",
        }

    def _effective_read_roots(self) -> tuple[Path, ...]:
        """All roots with read access (read_roots + write_roots)."""
        seen: list[Path] = []
        for r in (*self.read_roots, *self.write_roots):
            if r not in seen:
                seen.append(r)
        return tuple(seen)

    def _effective_write_roots(self) -> tuple[Path, ...]:
        return self.write_roots

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

            # Determine whether this is a read or write operation
            if tool_name in self._WRITE_TOOLS:
                roots = self._effective_write_roots()
                access_label = "write"
            else:
                roots = self._effective_read_roots()
                access_label = "read"

            if not self._is_inside_roots(target, roots):
                return ToolPolicyDecision(
                    allowed=False,
                    message=(
                        f"Tool '{tool_name}' path is outside configured "
                        f"{access_label} roots: {target}"
                    ),
                )
        return ToolPolicyDecision(allowed=True)

    def _check_cwd(self, arguments: dict[str, Any]) -> ToolPolicyDecision:
        raw_cwd = arguments.get("cwd", ".")
        cwd = Path(str(raw_cwd)).expanduser().resolve()
        # Commands can run in any readable directory
        if self._is_inside_roots(cwd, self._effective_read_roots()):
            return ToolPolicyDecision(allowed=True)
        return ToolPolicyDecision(
            allowed=False,
            message=f"Tool 'run_command' cwd is outside configured roots: {cwd}",
        )

    @staticmethod
    def _is_inside_roots(target: Path, roots: tuple[Path, ...]) -> bool:
        for root in roots:
            resolved_root = root.expanduser().resolve()
            try:
                target.relative_to(resolved_root)
                return True
            except ValueError:
                continue
        return False

    # Backward-compatible property
    def _is_inside_allowed_roots(self, target: Path) -> bool:
        return self._is_inside_roots(target, self._effective_read_roots())
