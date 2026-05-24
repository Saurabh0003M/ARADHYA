"""Unit tests for permission rules (src/aradhya/permission_rules.py)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.aradhya.permission_rules import (
    ConditionalBlockRule,
    PermissionDecision,
    PermissionEngine,
    PermissionRule,
    load_permissions,
    parse_rule,
)


class TestParseRule:
    def test_simple_tool_name(self) -> None:
        rule = parse_rule("read_file")
        assert rule is not None
        assert rule.tool_name == "read_file"
        assert rule.arg_pattern == ""

    def test_tool_with_pattern(self) -> None:
        rule = parse_rule("run_command(npm *)")
        assert rule is not None
        assert rule.tool_name == "run_command"
        assert rule.arg_pattern == "npm *"

    def test_tool_with_glob(self) -> None:
        rule = parse_rule("write_file(*.py)")
        assert rule is not None
        assert rule.tool_name == "write_file"
        assert rule.arg_pattern == "*.py"

    def test_empty_string_returns_none(self) -> None:
        assert parse_rule("") is None

    def test_invalid_format_returns_none(self) -> None:
        assert parse_rule("not a valid rule!!!") is None


class TestPermissionRuleMatching:
    def test_bare_tool_matches_any_args(self) -> None:
        rule = PermissionRule(tool_name="read_file")
        assert rule.matches("read_file", {"path": "/etc/hosts"})
        assert not rule.matches("write_file", {"path": "/etc/hosts"})

    def test_command_pattern_matches(self) -> None:
        rule = PermissionRule(tool_name="run_command", arg_pattern="npm *")
        assert rule.matches("run_command", {"command": "npm install"})
        assert rule.matches("run_command", {"command": "npm test"})
        assert not rule.matches("run_command", {"command": "pip install"})

    def test_wildcard_tool_matches_all(self) -> None:
        rule = PermissionRule(tool_name="*")
        assert rule.matches("read_file", {})
        assert rule.matches("run_command", {"command": "echo hi"})

    def test_file_path_pattern(self) -> None:
        rule = PermissionRule(tool_name="write_file", arg_pattern="*.py")
        assert rule.matches("write_file", {"path": "test.py"})
        assert not rule.matches("write_file", {"path": "test.js"})

    def test_git_command_pattern(self) -> None:
        rule = PermissionRule(tool_name="run_command", arg_pattern="git *")
        assert rule.matches("run_command", {"command": "git add ."})
        assert rule.matches("run_command", {"command": "git commit -m 'msg'"})
        assert not rule.matches("run_command", {"command": "rm -rf /"})

    def test_dangerous_rm_pattern(self) -> None:
        rule = PermissionRule(tool_name="run_command", arg_pattern="rm -rf *")
        assert rule.matches("run_command", {"command": "rm -rf /tmp/junk"})
        assert not rule.matches("run_command", {"command": "rm file.txt"})


class TestConditionalBlockRule:
    def test_blocks_when_pattern_does_not_match(self) -> None:
        rule = ConditionalBlockRule(
            tool_name="run_command",
            safe_pattern=r"radare2.*\s+-c\s+",
            raw="radare2 requires -c flag",
        )
        # radare2 without -c should be blocked
        assert rule.matches("run_command", {"command": "radare2 binary"})

    def test_allows_when_pattern_matches(self) -> None:
        rule = ConditionalBlockRule(
            tool_name="run_command",
            safe_pattern=r"radare2.*\s+-c\s+",
            raw="radare2 requires -c flag",
        )
        # radare2 with -c should pass
        assert not rule.matches("run_command", {"command": "radare2 -c 'pd 10' binary"})

    def test_does_not_match_other_tools(self) -> None:
        rule = ConditionalBlockRule(
            tool_name="run_command",
            safe_pattern=r"--safe",
            raw="test",
        )
        assert not rule.matches("write_file", {"path": "test.py"})

    def test_wildcard_tool_matches_all(self) -> None:
        rule = ConditionalBlockRule(
            tool_name="*",
            safe_pattern=r"--confirm",
            raw="all tools need --confirm",
        )
        # Without --confirm, should block
        assert rule.matches("run_command", {"command": "rm file"})
        # With --confirm, should allow
        assert not rule.matches("run_command", {"command": "rm file --confirm"})


class TestPermissionEngineWithConditionalBlocks:
    def test_conditional_block_denies(self) -> None:
        engine = PermissionEngine(
            conditional_blocks=[
                ConditionalBlockRule(
                    tool_name="run_command",
                    safe_pattern=r"python\s+-c\s+",
                    raw="python needs -c flag",
                ),
            ],
        )
        # python without -c should be blocked
        decision = engine.check("run_command", {"command": "python"})
        assert decision.allowed is False
        assert "conditional" in decision.reason.lower()

    def test_conditional_block_allows_safe(self) -> None:
        engine = PermissionEngine(
            conditional_blocks=[
                ConditionalBlockRule(
                    tool_name="run_command",
                    safe_pattern=r"python\s+-c\s+",
                    raw="python needs -c flag",
                ),
            ],
        )
        # python with -c should pass through
        decision = engine.check("run_command", {"command": "python -c 'print(1)'"})
        assert decision.allowed is True

    def test_deny_still_overrides_conditional(self) -> None:
        engine = PermissionEngine(
            deny_rules=[
                PermissionRule(tool_name="run_command", arg_pattern="rm *"),
            ],
            conditional_blocks=[
                ConditionalBlockRule(
                    tool_name="run_command",
                    safe_pattern=r"--safe",
                    raw="needs --safe",
                ),
            ],
        )
        # deny rule fires before conditional block
        decision = engine.check("run_command", {"command": "rm file --safe"})
        assert decision.allowed is False
        assert "deny rule" in decision.reason.lower()


class TestPermissionEngine:
    def test_no_rules_requires_confirmation(self) -> None:
        engine = PermissionEngine()
        decision = engine.check("run_command", {"command": "echo hi"})
        assert decision.allowed is True
        assert decision.requires_confirmation is True

    def test_allow_rule_skips_confirmation(self) -> None:
        engine = PermissionEngine(
            allow_rules=[PermissionRule(tool_name="run_command", arg_pattern="npm *")],
        )
        decision = engine.check("run_command", {"command": "npm test"})
        assert decision.allowed is True
        assert decision.requires_confirmation is False

    def test_deny_rule_blocks(self) -> None:
        engine = PermissionEngine(
            deny_rules=[PermissionRule(tool_name="run_command", arg_pattern="rm -rf *")],
        )
        decision = engine.check("run_command", {"command": "rm -rf /"})
        assert decision.allowed is False
        assert "deny rule" in decision.reason.lower()

    def test_deny_overrides_allow(self) -> None:
        """Critical security invariant: deny always wins over allow."""
        engine = PermissionEngine(
            allow_rules=[
                PermissionRule(tool_name="run_command", arg_pattern="*"),
            ],
            deny_rules=[
                PermissionRule(tool_name="run_command", arg_pattern="rm -rf *"),
            ],
        )
        # npm should be allowed
        assert engine.check("run_command", {"command": "npm test"}).allowed is True
        # rm -rf should be denied even though wildcard allows everything
        assert engine.check("run_command", {"command": "rm -rf /"}).allowed is False

    def test_no_match_falls_through(self) -> None:
        engine = PermissionEngine(
            allow_rules=[PermissionRule(tool_name="read_file")],
        )
        # write_file has no matching rule — should fall through to default
        decision = engine.check("write_file", {"path": "test.py"})
        assert decision.allowed is True
        assert decision.requires_confirmation is True

    def test_multiple_allow_rules(self) -> None:
        engine = PermissionEngine(
            allow_rules=[
                PermissionRule(tool_name="run_command", arg_pattern="npm *"),
                PermissionRule(tool_name="run_command", arg_pattern="git *"),
                PermissionRule(tool_name="read_file"),
            ],
        )
        assert engine.check("run_command", {"command": "npm test"}).allowed
        assert engine.check("run_command", {"command": "git status"}).allowed
        assert engine.check("read_file", {"path": "any.txt"}).allowed


class TestLoadPermissions:
    def test_load_from_file(self, tmp_path: Path) -> None:
        config_dir = tmp_path / ".aradhya"
        config_dir.mkdir()
        (config_dir / "permissions.json").write_text(
            json.dumps({
                "allow": ["run_command(npm *)", "read_file"],
                "deny": ["run_command(rm -rf *)"],
            }),
            encoding="utf-8",
        )
        engine = load_permissions(user_config_dir=config_dir)
        assert len(engine.allow_rules) == 2
        assert len(engine.deny_rules) == 1

    def test_missing_file_returns_empty_engine(self, tmp_path: Path) -> None:
        engine = load_permissions(user_config_dir=tmp_path / "nonexistent")
        assert len(engine.allow_rules) == 0
        assert len(engine.deny_rules) == 0

    def test_project_rules_additive(self, tmp_path: Path) -> None:
        user_dir = tmp_path / "user"
        user_dir.mkdir()
        (user_dir / "permissions.json").write_text(
            json.dumps({"allow": ["read_file"]}),
            encoding="utf-8",
        )

        project = tmp_path / "project"
        project_perms = project / ".aradhya"
        project_perms.mkdir(parents=True)
        (project_perms / "permissions.json").write_text(
            json.dumps({"allow": ["run_command(npm *)"], "deny": ["delete_file"]}),
            encoding="utf-8",
        )

        engine = load_permissions(
            project_root=project,
            user_config_dir=user_dir,
        )
        assert len(engine.allow_rules) == 2  # read_file + run_command(npm *)
        assert len(engine.deny_rules) == 1   # delete_file

    def test_invalid_json_returns_empty(self, tmp_path: Path) -> None:
        config_dir = tmp_path / ".aradhya"
        config_dir.mkdir()
        (config_dir / "permissions.json").write_text("BAD JSON", encoding="utf-8")
        engine = load_permissions(user_config_dir=config_dir)
        assert len(engine.allow_rules) == 0

    def test_load_block_unless_regex(self, tmp_path: Path) -> None:
        config_dir = tmp_path / ".aradhya"
        config_dir.mkdir()
        (config_dir / "permissions.json").write_text(
            json.dumps({
                "allow": [],
                "deny": [],
                "block_unless_regex": [
                    {"tool": "run_command", "safe_pattern": r"python\s+-c\s+"},
                ],
            }),
            encoding="utf-8",
        )
        engine = load_permissions(user_config_dir=config_dir)
        assert len(engine.conditional_blocks) == 1
        assert engine.conditional_blocks[0].tool_name == "run_command"

