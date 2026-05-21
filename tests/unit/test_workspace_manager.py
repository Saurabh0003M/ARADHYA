"""Unit tests for WorkspaceManager (workspace_manager.py)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.aradhya.workspace_manager import WorkspaceManager


class TestWorktreePaths:
    def test_worktree_path_uses_session_id(self, tmp_path: Path) -> None:
        mgr = WorkspaceManager(worktree_base=tmp_path)
        session_id = "abc123xyz456"
        project = Path("F:/ARADHYA")
        wt = mgr._worktree_path(project, session_id)
        assert "abc123xyz4" in str(wt)
        assert "ARADHYA" in str(wt)

    def test_worktree_path_truncates_session_id(self, tmp_path: Path) -> None:
        mgr = WorkspaceManager(worktree_base=tmp_path)
        long_id = "a" * 64
        wt = mgr._worktree_path(Path("F:/ARADHYA"), long_id)
        # Should only use first 12 chars of session_id
        parts = wt.parts
        assert all(len(p) <= 12 for p in parts if "a" * 12 in p)


class TestIsGitRepo:
    def test_git_repo_detected(self, tmp_path: Path) -> None:
        mgr = WorkspaceManager(worktree_base=tmp_path)
        # F:/ARADHYA is a real git repo
        result = mgr._is_git_repo(Path("F:/ARADHYA"))
        assert result is True

    def test_non_git_dir_not_detected(self, tmp_path: Path) -> None:
        mgr = WorkspaceManager(worktree_base=tmp_path)
        result = mgr._is_git_repo(tmp_path)
        assert result is False


class TestCreateWorktree:
    def test_skips_non_git_directory(self, tmp_path: Path) -> None:
        mgr = WorkspaceManager(worktree_base=tmp_path)
        result = mgr.create_worktree(
            project_root=tmp_path,
            session_id="session-001",
        )
        assert result is None

    def test_returns_path_for_git_repo(self, tmp_path: Path) -> None:
        mgr = WorkspaceManager(worktree_base=tmp_path)

        def fake_git(cwd: Path, args: list) -> dict:
            if args[0] == "rev-parse":
                return {"returncode": 0, "stdout": ".git", "stderr": ""}
            if args[0] == "worktree" and args[1] == "add":
                # Create the directory so it looks like it worked
                wt_path = Path(args[-1])
                wt_path.mkdir(parents=True, exist_ok=True)
                return {"returncode": 0, "stdout": "", "stderr": ""}
            return {"returncode": 0, "stdout": "", "stderr": ""}

        mgr._git = fake_git  # type: ignore[method-assign]
        result = mgr.create_worktree(
            project_root=tmp_path / "myproject",
            session_id="test-session-001",
        )
        assert result is not None
        assert result.exists()

    def test_returns_existing_path_without_recreating(self, tmp_path: Path) -> None:
        mgr = WorkspaceManager(worktree_base=tmp_path)
        session_id = "existing-session"
        fake_project = tmp_path / "myproject"
        wt = mgr._worktree_path(fake_project, session_id)
        wt.mkdir(parents=True, exist_ok=True)

        def fake_git_is_repo(cwd: Path, args: list) -> dict:
            if args[0] == "rev-parse":
                return {"returncode": 0, "stdout": ".git", "stderr": ""}
            return {"returncode": 1, "stdout": "", "stderr": ""}

        mgr._git = fake_git_is_repo  # type: ignore[method-assign]
        result = mgr.create_worktree(
            project_root=fake_project,
            session_id=session_id,
        )
        assert result == wt


class TestListWorktrees:
    def test_parses_porcelain_output(self, tmp_path: Path) -> None:
        mgr = WorkspaceManager(worktree_base=tmp_path)
        porcelain = (
            "worktree F:/ARADHYA\n"
            "HEAD abc1234\n"
            "branch refs/heads/main\n"
            "\n"
            "worktree C:/Users/saura/.aradhya/worktrees/abc123/ARADHYA\n"
            "HEAD def5678\n"
            "branch refs/heads/aradhya/session-abc123\n"
        )

        def fake_git(cwd: Path, args: list) -> dict:
            return {"returncode": 0, "stdout": porcelain, "stderr": ""}

        mgr._git = fake_git  # type: ignore[method-assign]
        trees = mgr.list_worktrees(Path("F:/ARADHYA"))
        assert len(trees) == 2
        assert trees[0]["path"] == "F:/ARADHYA"
        assert trees[1]["branch"] == "refs/heads/aradhya/session-abc123"
