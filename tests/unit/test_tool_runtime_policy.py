from __future__ import annotations

from src.aradhya.tools.file_tools import read_file, write_file
from src.aradhya.tools.runtime_policy import ToolRuntimePolicy
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
    assert "outside configured roots" in result.output
    assert not outside.exists()
