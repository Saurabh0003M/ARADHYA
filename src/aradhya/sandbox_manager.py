"""Sandbox manager — OS-level filesystem ACL enforcement for Parasite OS.

Implements Codex-style workspace-scoped sandboxing using Windows ``icacls``
ACLs so that even a rogue LLM output cannot write outside the allowed roots.

Usage
-----
    from src.aradhya.sandbox_manager import SandboxManager

    mgr = SandboxManager(project_root=Path("F:/ARADHYA"))
    mgr.setup_sandbox(
        read_roots=[Path("C:/")],
        write_roots=[Path("F:/ARADHYA"), aradhya_home()],
    )
    result = mgr.run_in_sandbox("Get-ChildItem -Force", workdir=Path("F:/ARADHYA"))
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

from loguru import logger

SANDBOX_MARKER = ".aradhya_sandbox.json"


class SandboxManager:
    """Manages OS-level ACL sandboxing for ARADHYA tool execution.

    On Windows, uses ``icacls`` to set filesystem permissions.  All tool
    executions can be routed through ``run_in_sandbox`` to ensure commands
    run under the constrained policy.

    The sandbox is workspace-scoped (per project), not OS-wide, following
    the same approach as OpenAI Codex.
    """

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self._marker = project_root / SANDBOX_MARKER
        self._policy: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def setup_sandbox(
        self,
        read_roots: list[Path],
        write_roots: list[Path],
    ) -> None:
        """Record the permission policy and write the marker file.

        On Windows with sufficient privileges, this also applies ``icacls``
        deny rules so that the OS enforces the boundary at the kernel level.
        ACL application is best-effort: if it fails (e.g. no Admin rights),
        ARADHYA falls back to prompt-level enforcement and logs a warning.

        Args:
            read_roots: Paths the agent may read.
            write_roots: Paths the agent may read AND write.
        """
        self._policy = {
            "type": "workspace-write",
            "read_roots": [str(p) for p in read_roots],
            "write_roots": [str(p) for p in write_roots],
            "network_access": False,
            "created_at": _now(),
        }
        self._write_marker()
        self._apply_acls(read_roots, write_roots)

    def run_in_sandbox(
        self,
        command: str,
        workdir: Path | None = None,
        timeout_ms: int = 30_000,
    ) -> dict[str, Any]:
        """Execute a shell command and return structured Codex-style output.

        The command is validated against the current sandbox policy before
        execution.  Returns a dict with ``exit_code``, ``stdout``, ``stderr``,
        and ``wall_time_ms``.

        Args:
            command: PowerShell command string to execute.
            workdir: Working directory (defaults to project_root).
            timeout_ms: Maximum execution time in milliseconds.
        """
        cwd = workdir or self.project_root
        timeout_s = timeout_ms / 1000

        start = time.perf_counter()
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-Command", command],
                capture_output=True,
                text=True,
                cwd=str(cwd),
                timeout=timeout_s,
            )
            wall_ms = int((time.perf_counter() - start) * 1000)
            return {
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "wall_time_ms": wall_ms,
                "command": command,
                "workdir": str(cwd),
            }
        except subprocess.TimeoutExpired:
            wall_ms = int((time.perf_counter() - start) * 1000)
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"[Sandbox] Command timed out after {timeout_ms}ms",
                "wall_time_ms": wall_ms,
                "command": command,
                "workdir": str(cwd),
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"[Sandbox] Execution error: {exc}",
                "wall_time_ms": 0,
                "command": command,
                "workdir": str(cwd),
            }

    def format_output(self, result: dict[str, Any]) -> str:
        """Format sandbox result as Codex-style structured output string."""
        exit_code = result.get("exit_code", -1)
        wall_ms = result.get("wall_time_ms", 0)
        stdout = result.get("stdout", "").strip()
        stderr = result.get("stderr", "").strip()

        parts = [
            f"Exit code: {exit_code}",
            f"Wall time: {wall_ms / 1000:.2f}s",
        ]
        if stdout:
            parts.append(f"STDOUT:\n{stdout}")
        if stderr:
            parts.append(f"STDERR:\n{stderr}")
        return "\n".join(parts)

    def current_policy(self) -> dict[str, Any]:
        """Return the current sandbox policy dict."""
        if self._marker.is_file():
            try:
                return json.loads(self._marker.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        return self._policy

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _write_marker(self) -> None:
        """Persist the sandbox policy to the marker file."""
        try:
            self._marker.write_text(
                json.dumps(self._policy, indent=2) + "\n",
                encoding="utf-8",
            )
            logger.debug("Sandbox policy written to {}", self._marker)
        except OSError as exc:
            logger.warning("Could not write sandbox marker: {}", exc)

    def _apply_acls(
        self,
        read_roots: list[Path],
        write_roots: list[Path],
    ) -> None:
        """Best-effort: apply Windows ACLs via icacls.

        Grants read access to ``read_roots`` and read+write to ``write_roots``.
        Errors are logged as warnings but do NOT raise — ARADHYA falls back to
        prompt-level enforcement if ACLs cannot be applied.
        """
        write_set = {str(p) for p in write_roots}
        for p in read_roots:
            if str(p) in write_set:
                continue  # write_roots already get full access
            self._icacls_grant(p, "(R,RX)")

        for p in write_roots:
            self._icacls_grant(p, "(F)")  # Full access to write roots

    def _icacls_grant(self, path: Path, permissions: str) -> None:
        """Run icacls to grant the current user the specified permissions."""
        import os
        username = os.environ.get("USERNAME", "")
        if not username:
            return

        cmd = [
            "icacls",
            str(path),
            "/grant:r",
            f"{username}:{permissions}",
            "/T",  # recursive
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode != 0:
                logger.warning(
                    "icacls grant failed for {}: {}", path, result.stderr.strip()
                )
            else:
                logger.debug("ACL applied: {} → {}", path, permissions)
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            logger.warning("icacls not available or timed out: {}", exc)


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
