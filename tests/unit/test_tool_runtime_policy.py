from __future__ import annotations

from src.aradhya.tools.file_tools import read_file, write_file
from src.aradhya.tools.runtime_policy import ToolRuntimePolicy
from src.aradhya.tools.shell_tools import run_command
from src.aradhya.tools.tool_registry import ToolRegistry


def build_registry(policy: ToolRuntimePolicy) -> ToolRegistry:
    registry = ToolRegistry(policy=policy)
    registry.register_function(read_file)
    registry.register_function(write_file)
    return registry


def test_policy_allows_read_inside_configured_roots(tmp_path):
    target = tmp_path / "note.txt"
    target.write_text("hello", encoding="utf-8")
    registry = build_registry(ToolRuntimePolicy(allowed_roots=(tmp_path,)))

    result = registry.execute_tool("read_file", {"path": str(target)})

    assert result.success is True
    assert result.output == "hello"


def test_policy_blocks_write_without_confirmed_live_execution(tmp_path):
    registry = build_registry(
        ToolRuntimePolicy(
            allowed_roots=(tmp_path,),
            live_execution_enabled=False,
            mutation_granted=True,
        )
    )

    result = registry.execute_tool(
        "write_file",
        {"path": str(tmp_path / "new.txt"), "content": "hello"},
    )

    assert result.success is False
    assert result.requires_confirmation is True
    assert "allow_live_execution is false" in result.output


def test_policy_allows_write_with_confirmed_live_execution(tmp_path):
    target = tmp_path / "new.txt"
    registry = build_registry(
        ToolRuntimePolicy(
            allowed_roots=(tmp_path,),
            live_execution_enabled=True,
            mutation_granted=True,
        )
    )

    result = registry.execute_tool(
        "write_file",
        {"path": str(target), "content": "hello"},
    )

    assert result.success is True
    assert target.read_text(encoding="utf-8") == "hello"


def test_policy_blocks_file_tools_outside_configured_roots(tmp_path):
    outside = tmp_path.parent / "outside.txt"
    registry = build_registry(
        ToolRuntimePolicy(
            allowed_roots=(tmp_path,),
            live_execution_enabled=True,
            mutation_granted=True,
        )
    )

    result = registry.execute_tool(
        "write_file",
        {"path": str(outside), "content": "blocked"},
    )

    assert result.success is False
    assert "outside configured" in result.output
    assert not outside.exists()


def test_policy_allows_read_but_blocks_write_in_read_only_root(tmp_path):
    """Workspace-write model: reads are broad, writes confined to write_roots."""
    read_only = tmp_path / "documents"
    workspace = tmp_path / "workspace"
    read_only.mkdir()
    workspace.mkdir()
    existing = read_only / "note.txt"
    existing.write_text("hello", encoding="utf-8")

    registry = build_registry(
        ToolRuntimePolicy(
            read_roots=(read_only, workspace),
            write_roots=(workspace,),
            live_execution_enabled=True,
            mutation_granted=True,
        )
    )

    # Reading inside a read-only root succeeds.
    read_result = registry.execute_tool("read_file", {"path": str(existing)})
    assert read_result.success is True
    assert read_result.output == "hello"

    # Writing inside that same read-only root is denied — it is not a write root.
    blocked = registry.execute_tool(
        "write_file",
        {"path": str(read_only / "blocked.txt"), "content": "nope"},
    )
    assert blocked.success is False
    assert "outside configured write roots" in blocked.output
    assert not (read_only / "blocked.txt").exists()

    # Writing inside the workspace (a write root) succeeds.
    allowed = registry.execute_tool(
        "write_file",
        {"path": str(workspace / "ok.txt"), "content": "yes"},
    )
    assert allowed.success is True
    assert (workspace / "ok.txt").read_text(encoding="utf-8") == "yes"


def test_run_command_cwd_outside_roots_is_blocked(tmp_path):
    """run_command is refused when its cwd is outside the configured roots.

    The policy check runs before the handler, so no subprocess is spawned.
    """
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()

    registry = ToolRegistry(
        policy=ToolRuntimePolicy(
            read_roots=(workspace,),
            write_roots=(workspace,),
            live_execution_enabled=True,
            mutation_granted=True,
        )
    )
    registry.register_function(run_command)

    result = registry.execute_tool(
        "run_command",
        {"command": "echo hi", "cwd": str(outside)},
    )
    assert result.success is False
    assert "cwd is outside configured roots" in result.output
