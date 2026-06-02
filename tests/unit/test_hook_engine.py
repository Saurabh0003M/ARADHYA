"""Unit tests for the hook engine (src/aradhya/hooks/hook_engine.py)."""

from __future__ import annotations

import json
from pathlib import Path


from src.aradhya.hooks.hook_engine import (
    HookDecision,
    HookDefinition,
    HookEngine,
    HookEvent,
    HookType,
)
from src.aradhya.hooks.hook_config import (
    load_hooks,
    load_hooks_from_file,
    create_default_hooks_config,
)

# ── Hook Engine: Callable hooks ────────────────────────────────────────────


class TestHookEngineCallable:
    def test_empty_engine_returns_allow(self) -> None:
        engine = HookEngine()
        result = engine.fire(HookEvent.PRE_TOOL_USE, {"tool_name": "read_file"})
        assert result.decision == HookDecision.ALLOW

    def test_callable_hook_fires(self) -> None:
        called_with: dict = {}

        def my_hook(payload: dict) -> dict:
            called_with.update(payload)
            return {"decision": "allow", "systemMessage": "Hook ran!"}

        engine = HookEngine()
        engine.register(
            HookDefinition(
                event=HookEvent.PRE_TOOL_USE,
                hook_type=HookType.CALLABLE,
                callable_fn=my_hook,
            )
        )
        result = engine.fire(
            HookEvent.PRE_TOOL_USE,
            {"tool_name": "run_command", "tool_input": {"command": "echo hi"}},
        )
        assert result.decision == HookDecision.ALLOW
        assert result.system_message == "Hook ran!"
        assert called_with["tool_name"] == "run_command"

    def test_deny_decision_blocks(self) -> None:
        def deny_hook(payload: dict) -> dict:
            return {"decision": "deny", "systemMessage": "Blocked!"}

        engine = HookEngine()
        engine.register(
            HookDefinition(
                event=HookEvent.PRE_TOOL_USE,
                hook_type=HookType.CALLABLE,
                callable_fn=deny_hook,
            )
        )
        result = engine.fire(
            HookEvent.PRE_TOOL_USE,
            {"tool_name": "run_command"},
        )
        assert result.decision == HookDecision.DENY
        assert result.system_message == "Blocked!"

    def test_first_deny_wins(self) -> None:
        """When multiple hooks are registered, the first deny stops evaluation."""

        def allow_hook(payload: dict) -> dict:
            return {"decision": "allow"}

        def deny_hook(payload: dict) -> dict:
            return {"decision": "deny", "systemMessage": "Denied by hook 2"}

        def never_reached(payload: dict) -> dict:
            raise AssertionError("This hook should not run")

        engine = HookEngine()
        for fn in [allow_hook, deny_hook, never_reached]:
            engine.register(
                HookDefinition(
                    event=HookEvent.PRE_TOOL_USE,
                    hook_type=HookType.CALLABLE,
                    callable_fn=fn,
                )
            )
        result = engine.fire(HookEvent.PRE_TOOL_USE, {"tool_name": "write_file"})
        assert result.decision == HookDecision.DENY

    def test_matcher_filters_by_tool_name(self) -> None:
        call_count = 0

        def counting_hook(payload: dict) -> dict:
            nonlocal call_count
            call_count += 1
            return {}

        engine = HookEngine()
        engine.register(
            HookDefinition(
                event=HookEvent.PRE_TOOL_USE,
                hook_type=HookType.CALLABLE,
                callable_fn=counting_hook,
                matcher="run_command",
            )
        )
        # Should NOT fire for read_file
        engine.fire(HookEvent.PRE_TOOL_USE, {"tool_name": "read_file"})
        assert call_count == 0

        # Should fire for run_command
        engine.fire(HookEvent.PRE_TOOL_USE, {"tool_name": "run_command"})
        assert call_count == 1

    def test_once_hook_fires_only_once(self) -> None:
        call_count = 0

        def counting_hook(payload: dict) -> dict:
            nonlocal call_count
            call_count += 1
            return {"systemMessage": f"call {call_count}"}

        engine = HookEngine()
        engine.register(
            HookDefinition(
                event=HookEvent.SESSION_START,
                hook_type=HookType.CALLABLE,
                callable_fn=counting_hook,
                once=True,
            )
        )
        engine.fire(HookEvent.SESSION_START, {})
        engine.fire(HookEvent.SESSION_START, {})
        engine.fire(HookEvent.SESSION_START, {})
        assert call_count == 1

    def test_fail_open_on_exception(self) -> None:
        def broken_hook(payload: dict) -> dict:
            raise RuntimeError("Hook crashed!")

        engine = HookEngine()
        engine.register(
            HookDefinition(
                event=HookEvent.PRE_TOOL_USE,
                hook_type=HookType.CALLABLE,
                callable_fn=broken_hook,
            )
        )
        result = engine.fire(HookEvent.PRE_TOOL_USE, {"tool_name": "run_command"})
        # Must fail-open
        assert result.decision == HookDecision.ALLOW
        assert "Hook crashed" in result.error

    def test_updated_input_propagates(self) -> None:
        def modify_hook(payload: dict) -> dict:
            return {
                "decision": "allow",
                "updatedInput": {"command": "echo safe"},
            }

        engine = HookEngine()
        engine.register(
            HookDefinition(
                event=HookEvent.PRE_TOOL_USE,
                hook_type=HookType.CALLABLE,
                callable_fn=modify_hook,
            )
        )
        result = engine.fire(
            HookEvent.PRE_TOOL_USE,
            {"tool_name": "run_command", "tool_input": {"command": "rm -rf /"}},
        )
        assert result.updated_input == {"command": "echo safe"}

    def test_post_tool_use_updated_output(self) -> None:
        def sanitize_hook(payload: dict) -> dict:
            return {"updatedOutput": "[REDACTED]"}

        engine = HookEngine()
        engine.register(
            HookDefinition(
                event=HookEvent.POST_TOOL_USE,
                hook_type=HookType.CALLABLE,
                callable_fn=sanitize_hook,
            )
        )
        result = engine.fire(
            HookEvent.POST_TOOL_USE,
            {"tool_name": "run_command", "output": "secret_key=abc123"},
        )
        assert result.updated_output == "[REDACTED]"

    def test_clear_specific_event(self) -> None:
        engine = HookEngine()
        engine.register(
            HookDefinition(
                event=HookEvent.PRE_TOOL_USE,
                hook_type=HookType.CALLABLE,
                callable_fn=lambda p: {},
            )
        )
        engine.register(
            HookDefinition(
                event=HookEvent.STOP,
                hook_type=HookType.CALLABLE,
                callable_fn=lambda p: {},
            )
        )
        assert engine.total_hooks == 2
        engine.clear(HookEvent.PRE_TOOL_USE)
        assert engine.total_hooks == 1
        assert len(engine.hooks_for(HookEvent.PRE_TOOL_USE)) == 0
        assert len(engine.hooks_for(HookEvent.STOP)) == 1


# ── Hook Config: loading from JSON ────────────────────────────────────────


class TestHookConfig:
    def test_load_empty_directory(self, tmp_path: Path) -> None:
        hooks = load_hooks_from_file(tmp_path / "nonexistent.json")
        assert hooks == []

    def test_load_valid_hooks_json(self, tmp_path: Path) -> None:
        config = {
            "hooks": {
                "PreToolUse": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": "python pretooluse.py",
                                "timeout": 5,
                                "matcher": "run_command",
                            }
                        ]
                    }
                ],
                "Stop": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": "python stop.py",
                                "once": True,
                            }
                        ]
                    }
                ],
            }
        }
        hooks_file = tmp_path / "hooks.json"
        hooks_file.write_text(json.dumps(config), encoding="utf-8")

        definitions = load_hooks_from_file(hooks_file)
        assert len(definitions) == 2

        pre = [d for d in definitions if d.event == HookEvent.PRE_TOOL_USE]
        assert len(pre) == 1
        assert pre[0].matcher == "run_command"
        assert pre[0].timeout_seconds == 5

        stop = [d for d in definitions if d.event == HookEvent.STOP]
        assert len(stop) == 1
        assert stop[0].once is True

    def test_load_hooks_replaces_root_var(self, tmp_path: Path) -> None:
        config = {
            "hooks": {
                "PreToolUse": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": "python ${ARADHYA_HOOKS_ROOT}/myhook.py",
                            }
                        ]
                    }
                ]
            }
        }
        hooks_file = tmp_path / "hooks.json"
        hooks_file.write_text(json.dumps(config), encoding="utf-8")

        definitions = load_hooks_from_file(hooks_file)
        assert len(definitions) == 1
        assert str(tmp_path) in definitions[0].command

    def test_load_hooks_from_user_and_project(self, tmp_path: Path) -> None:
        user_dir = tmp_path / "user_hooks"
        user_dir.mkdir()
        (user_dir / "hooks.json").write_text(
            json.dumps(
                {
                    "hooks": {
                        "SessionStart": [{"hooks": [{"type": "command", "command": "echo user"}]}]
                    }
                }
            ),
            encoding="utf-8",
        )

        project_dir = tmp_path / "project" / ".aradhya" / "hooks"
        project_dir.mkdir(parents=True)
        (project_dir / "hooks.json").write_text(
            json.dumps(
                {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo project"}]}]}}
            ),
            encoding="utf-8",
        )

        engine = load_hooks(
            project_root=tmp_path / "project",
            user_hooks_dir=user_dir,
        )
        assert engine.total_hooks == 2

    def test_create_default_hooks_config(self, tmp_path: Path) -> None:
        hooks_dir = tmp_path / "hooks"
        path = create_default_hooks_config(hooks_dir)
        assert path.is_file()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "hooks" in data
        assert "PreToolUse" in data["hooks"]

    def test_invalid_json_returns_empty(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "hooks.json"
        bad_file.write_text("NOT VALID JSON!!!", encoding="utf-8")
        hooks = load_hooks_from_file(bad_file)
        assert hooks == []

    def test_unknown_event_skipped(self, tmp_path: Path) -> None:
        config = {
            "hooks": {"UnknownEvent": [{"hooks": [{"type": "command", "command": "echo x"}]}]}
        }
        hooks_file = tmp_path / "hooks.json"
        hooks_file.write_text(json.dumps(config), encoding="utf-8")
        definitions = load_hooks_from_file(hooks_file)
        assert definitions == []
