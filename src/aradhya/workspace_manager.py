"""Workspace Manager — Git worktree isolation for Parasite OS.

Creates isolated Git worktrees for each ARADHYA session so that agent
actions never touch the user's active working directory.

Modeled after OpenAI Codex's worktree approach:
    ~/.codex/worktrees/<hash>/<project>/  ← isolated shallow clone

ARADHYA stores worktrees at:
    ~/.aradhya/worktrees/<session_id>/<project_name>/

Usage
-----
    from src.aradhya.workspace_manager import WorkspaceManager

    mgr = WorkspaceManager()
    worktree = mgr.create_worktree(
        project_root=Path("F:/ARADHYA"),
        session_id="abc123",
        branch_name="aradhya/session-abc123",
    )
    # Agent now works in ``worktree`` instead of the live project
"""

from __future__ import annotations

import subprocess
import shutil
from pathlib import Path
from typing import Any

from loguru import logger

from src.aradhya.paths import worktrees_dir


class WorkspaceManager:
    """Manages Git worktrees for isolated agent sessions.

    Each session gets a dedicated worktree in ``~/.aradhya/worktrees/``.
    The agent reads/writes to the worktree; the user's live repo is untouched
    until the user explicitly merges/reviews the changes.
    """

    def __init__(self, worktree_base: Path | None = None) -> None:
        self._base = worktree_base or worktrees_dir()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_worktree(
        self,
        project_root: Path,
        session_id: str,
        branch_name: str | None = None,
    ) -> Path | None:
        """Create a Git worktree for the given session.

        Args:
            project_root: The root of the Git repository.
            session_id: Unique session identifier (used to name the worktree).
            branch_name: Branch to create/use. Defaults to
                ``aradhya/session-<session_id>``.

        Returns:
            Path to the created worktree directory, or None if Git is not
            available or the directory is not a Git repository.
        """
        if not self._is_git_repo(project_root):
            logger.warning(
                "WorkspaceManager: {} is not a Git repository; " "skipping worktree creation.",
                project_root,
            )
            return None

        branch = branch_name or f"aradhya/session-{session_id[:8]}"
        worktree_path = self._worktree_path(project_root, session_id)

        if worktree_path.exists():
            logger.info("Worktree already exists at {}", worktree_path)
            return worktree_path

        worktree_path.mkdir(parents=True, exist_ok=True)

        # Try creating a new detached worktree from current HEAD
        result = self._git(
            project_root,
            ["worktree", "add", "--detach", str(worktree_path)],
        )

        if result["returncode"] != 0:
            # Fallback: create a new branch from HEAD
            logger.debug(
                "Detached worktree failed ({}); trying with new branch",
                result["stderr"].strip(),
            )
            self._git(project_root, ["branch", branch])
            result = self._git(
                project_root,
                ["worktree", "add", str(worktree_path), branch],
            )

        if result["returncode"] != 0:
            logger.error(
                "Failed to create worktree at {}: {}",
                worktree_path,
                result["stderr"].strip(),
            )
            shutil.rmtree(worktree_path, ignore_errors=True)
            return None

        logger.info("Created Git worktree at {}", worktree_path)
        return worktree_path

    def remove_worktree(
        self,
        project_root: Path,
        session_id: str,
    ) -> bool:
        """Remove the worktree for a completed session.

        Args:
            project_root: The root of the Git repository.
            session_id: Session identifier whose worktree to remove.

        Returns:
            True if the worktree was removed successfully.
        """
        worktree_path = self._worktree_path(project_root, session_id)
        if not worktree_path.exists():
            return True

        result = self._git(
            project_root,
            ["worktree", "remove", "--force", str(worktree_path)],
        )
        if result["returncode"] == 0:
            logger.info("Removed worktree at {}", worktree_path)
            return True

        # Fallback: manual removal
        shutil.rmtree(worktree_path, ignore_errors=True)
        self._git(project_root, ["worktree", "prune"])
        return True

    def list_worktrees(self, project_root: Path) -> list[dict[str, Any]]:
        """List all active worktrees for a repository.

        Returns:
            List of dicts with ``path``, ``branch``, and ``head`` keys.
        """
        result = self._git(project_root, ["worktree", "list", "--porcelain"])
        if result["returncode"] != 0:
            return []

        worktrees: list[dict[str, Any]] = []
        current: dict[str, Any] = {}
        for line in result["stdout"].splitlines():
            if line.startswith("worktree "):
                if current:
                    worktrees.append(current)
                current = {"path": line[len("worktree ") :].strip()}
            elif line.startswith("HEAD "):
                current["head"] = line[len("HEAD ") :].strip()
            elif line.startswith("branch "):
                current["branch"] = line[len("branch ") :].strip()
            elif line == "bare":
                current["bare"] = True
        if current:
            worktrees.append(current)

        return worktrees

    def worktree_exists(self, project_root: Path, session_id: str) -> bool:
        """Return True if the worktree directory exists for this session."""
        return self._worktree_path(project_root, session_id).is_dir()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _worktree_path(self, project_root: Path, session_id: str) -> Path:
        """Return the canonical worktree path for a project + session."""
        short_id = session_id[:12]
        return self._base / short_id / project_root.name

    def _is_git_repo(self, path: Path) -> bool:
        """Return True if path is inside a Git repository."""
        result = self._git(path, ["rev-parse", "--git-dir"])
        return result["returncode"] == 0

    def _git(self, cwd: Path, args: list[str]) -> dict[str, Any]:
        """Run a git command and return a result dict."""
        if not shutil.which("git"):
            return {"returncode": 1, "stdout": "", "stderr": "git not found"}
        try:
            proc = subprocess.run(
                ["git"] + args,
                capture_output=True,
                text=True,
                cwd=str(cwd),
                timeout=30,
                check=False,
            )
            return {
                "returncode": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            }
        except subprocess.TimeoutExpired:
            return {"returncode": -1, "stdout": "", "stderr": "git timed out"}
        except Exception as exc:  # noqa: BLE001
            return {"returncode": -1, "stdout": "", "stderr": str(exc)}
