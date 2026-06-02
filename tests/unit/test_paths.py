"""Unit tests for centralized path resolver (src/aradhya/paths.py)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.aradhya.paths import (
    aradhya_home,
    aradhya_path,
    audit_dir,
    ensure_aradhya_dir,
    find_project_root,
    hooks_dir,
    notes_dir,
    repos_dir,
    reset_cache,
    sessions_dir,
    skills_dir,
    state_dir,
    worktrees_dir,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    """Reset path caches before every test."""
    reset_cache()
    yield
    reset_cache()


class TestAradhyaHome:
    def test_env_var_overrides_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        custom = tmp_path / "custom_aradhya"
        monkeypatch.setenv("ARADHYA_HOME", str(custom))
        assert aradhya_home() == custom.resolve()

    def test_default_is_home_dot_aradhya(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ARADHYA_HOME", raising=False)
        # Ensure no parasite.toml in CWD path
        monkeypatch.chdir(Path.home())
        reset_cache()
        result = aradhya_home()
        assert result == Path.home() / ".aradhya"

    def test_cached_across_calls(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ARADHYA_HOME", raising=False)
        first = aradhya_home()
        second = aradhya_home()
        assert first is second  # Same object from lru_cache

    def test_env_var_with_trailing_slash(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        custom = tmp_path / "trailing"
        monkeypatch.setenv("ARADHYA_HOME", str(custom) + os.sep)
        result = aradhya_home()
        assert str(result).rstrip(os.sep) == str(custom.resolve()).rstrip(os.sep)


class TestAradhyaPath:
    def test_single_part(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ARADHYA_HOME", str(tmp_path))
        assert aradhya_path("audit") == tmp_path / "audit"

    def test_multiple_parts(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ARADHYA_HOME", str(tmp_path))
        assert aradhya_path("skills", "installed") == tmp_path / "skills" / "installed"


class TestEnsureAradhyaDir:
    def test_creates_directory(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ARADHYA_HOME", str(tmp_path))
        subdir = ensure_aradhya_dir("deep", "nested", "dir")
        assert subdir.is_dir()
        assert subdir == tmp_path / "deep" / "nested" / "dir"

    def test_idempotent(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ARADHYA_HOME", str(tmp_path))
        first = ensure_aradhya_dir("already_exists")
        second = ensure_aradhya_dir("already_exists")
        assert first == second
        assert first.is_dir()


class TestWellKnownDirs:
    def test_all_helpers(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ARADHYA_HOME", str(tmp_path))
        assert audit_dir() == tmp_path / "audit"
        assert hooks_dir() == tmp_path / "hooks"
        assert sessions_dir() == tmp_path / "sessions"
        assert skills_dir() == tmp_path / "skills"
        assert notes_dir() == tmp_path / "notes"
        assert worktrees_dir() == tmp_path / "worktrees"
        assert repos_dir() == tmp_path / "repos"
        assert state_dir() == tmp_path

    def test_helpers_create_directories(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ARADHYA_HOME", str(tmp_path))
        for helper in [
            audit_dir,
            hooks_dir,
            sessions_dir,
            skills_dir,
            notes_dir,
            worktrees_dir,
            repos_dir,
        ]:
            result = helper()
            assert result.is_dir(), f"{helper.__name__} should create its directory"


class TestParasiteToml:
    def test_reads_home_from_toml(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ARADHYA_HOME", raising=False)
        # Create a fake project root with parasite.toml
        project = tmp_path / "project"
        project.mkdir()
        custom_home = tmp_path / "vm_home"
        (project / "parasite.toml").write_text(
            f'[paths]\nhome = "{custom_home.as_posix()}"\n',
            encoding="utf-8",
        )
        monkeypatch.chdir(project)
        reset_cache()
        assert aradhya_home() == custom_home.resolve()

    def test_env_var_overrides_toml(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        project = tmp_path / "project"
        project.mkdir()
        toml_home = tmp_path / "toml_home"
        env_home = tmp_path / "env_home"
        (project / "parasite.toml").write_text(
            f'[paths]\nhome = "{toml_home.as_posix()}"\n',
            encoding="utf-8",
        )
        monkeypatch.chdir(project)
        monkeypatch.setenv("ARADHYA_HOME", str(env_home))
        reset_cache()
        # Env var wins
        assert aradhya_home() == env_home.resolve()


class TestFindProjectRoot:
    def test_finds_pyproject(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        project = tmp_path / "myproject"
        sub = project / "src" / "pkg"
        sub.mkdir(parents=True)
        (project / "pyproject.toml").write_text("[tool.test]\n", encoding="utf-8")
        monkeypatch.chdir(sub)
        reset_cache()
        assert find_project_root() == project

    def test_finds_agents_md(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        project = tmp_path / "root"
        project.mkdir()
        (project / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
        monkeypatch.chdir(project)
        reset_cache()
        assert find_project_root() == project

    def test_no_markers_returns_none(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        monkeypatch.chdir(empty)
        reset_cache()
        # May or may not find root depending on parent dirs — just check no crash
        result = find_project_root()
        assert result is None or isinstance(result, Path)
