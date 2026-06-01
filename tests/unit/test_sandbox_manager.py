"""Unit tests for SandboxManager (sandbox_manager.py)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.aradhya.sandbox_manager import SandboxManager, SANDBOX_MARKER


class TestSandboxManagerPolicy:
    def test_setup_writes_marker(self, tmp_path: Path) -> None:
        mgr = SandboxManager(project_root=tmp_path)
        with patch.object(mgr, "_apply_acls"):
            mgr.setup_sandbox(
                read_roots=[Path("C:/")],
                write_roots=[tmp_path],
            )
        marker = tmp_path / SANDBOX_MARKER
        assert marker.is_file()
        policy = json.loads(marker.read_text(encoding="utf-8"))
        assert policy["type"] == "workspace-write"
        assert str(tmp_path) in policy["write_roots"]
        assert any("C:" in r for r in policy["read_roots"])

    def test_current_policy_reads_marker(self, tmp_path: Path) -> None:
        mgr = SandboxManager(project_root=tmp_path)
        with patch.object(mgr, "_apply_acls"):
            mgr.setup_sandbox(read_roots=[], write_roots=[tmp_path])
        policy = mgr.current_policy()
        assert policy["type"] == "workspace-write"

    def test_current_policy_empty_when_no_marker(self, tmp_path: Path) -> None:
        mgr = SandboxManager(project_root=tmp_path)
        policy = mgr.current_policy()
        assert policy == {}


class TestSandboxManagerRunCommand:
    @patch("subprocess.run")
    def test_run_echo_command(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="hello\n", stderr="")
        mgr = SandboxManager(project_root=tmp_path)
        result = mgr.run_in_sandbox("echo hello", workdir=tmp_path)
        assert result["exit_code"] == 0
        assert "hello" in result["stdout"]
        assert result["wall_time_ms"] >= 0

    @patch("subprocess.run")
    def test_run_failing_command(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        mgr = SandboxManager(project_root=tmp_path)
        result = mgr.run_in_sandbox(
            "exit 1", workdir=tmp_path
        )
        assert result["exit_code"] != 0

    @patch("subprocess.run")
    def test_timeout_returns_error(self, mock_run: MagicMock, tmp_path: Path) -> None:
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="Start-Sleep", timeout=0.2)
        mgr = SandboxManager(project_root=tmp_path)
        result = mgr.run_in_sandbox(
            "Start-Sleep -Seconds 10", workdir=tmp_path, timeout_ms=200
        )
        assert result["exit_code"] == -1
        assert "timed out" in result["stderr"].lower()

    @patch("subprocess.run")
    def test_format_output_includes_exit_code(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="formatted\n", stderr="")
        mgr = SandboxManager(project_root=tmp_path)
        result = mgr.run_in_sandbox("echo formatted", workdir=tmp_path)
        output = mgr.format_output(result)
        assert "Exit code:" in output
        assert "Wall time:" in output


class TestSandboxACLConstruction:
    @patch("os.environ.get")
    def test_apply_acls_calls_icacls(self, mock_getenv: MagicMock, tmp_path: Path) -> None:
        """ACL application should call icacls for each path."""
        # Provide a fake USERNAME so the icacls logic executes
        mock_getenv.return_value = "TestUser"
        mgr = SandboxManager(project_root=tmp_path)
        with patch("subprocess.run") as mock_run, patch("os.environ.get", return_value="fakeuser"):
            mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")
            mgr._apply_acls([], [tmp_path])
        # icacls should have been called for the write root
        calls = [str(c) for c in mock_run.call_args_list]
        assert any("icacls" in c for c in calls)

    def test_read_only_root_excluded_from_write_grant(self, tmp_path: Path) -> None:
        """Paths in both read and write sets should get write grant only."""
        mgr = SandboxManager(project_root=tmp_path)
        called_paths: list[str] = []
        original_grant = mgr._icacls_grant

        def recording_grant(path: Path, permissions: str) -> None:
            called_paths.append(f"{path}:{permissions}")

        mgr._icacls_grant = recording_grant  # type: ignore[method-assign]
        mgr._apply_acls(
            read_roots=[tmp_path],
            write_roots=[tmp_path],
        )
        # tmp_path should only appear once (write grant), not twice
        assert len(called_paths) == 1
        assert "(F)" in called_paths[0]
