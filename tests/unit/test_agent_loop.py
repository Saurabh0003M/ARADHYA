from __future__ import annotations

from typing import Any

from src.aradhya.agent_loop import AgentLoop, ToolResult
from src.aradhya.model_provider import ModelChatResult, ModelResult, ModelToolCall


class FakeExecutor:
    def __init__(self):
        self.calls: list[tuple[str, dict[str, Any], str]] = []

    def execute_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        tool_call_id: str = "",
    ) -> ToolResult:
        self.calls.append((name, arguments, tool_call_id))
        return ToolResult(
            tool_call_id=tool_call_id,
            name=name,
            output=f"{name} output",
            success=True,
        )

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read a file",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]


class NativeToolProvider:
    def __init__(self):
        self.calls = 0

    def chat(self, messages, *, tools=None, system_prompt=None):
        self.calls += 1
        if self.calls == 1:
            return ModelChatResult(
                text="",
                model="fake",
                provider="fake",
                raw={},
                tool_calls=(
                    ModelToolCall(
                        name="read_file",
                        arguments={"path": "README.md"},
                        id="call_1",
                    ),
                ),
            )
        return ModelChatResult(
            text="Read the file and found the answer.",
            model="fake",
            provider="fake",
            raw={},
        )


class TextToolProvider:
    def __init__(self, responses: list[str]):
        self.responses = responses
        self.calls = 0

    def generate(self, prompt: str, *, system_prompt: str | None = None) -> ModelResult:
        response = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return ModelResult(text=response, model="fake", provider="fake", raw={})


def test_agent_loop_executes_native_tool_calls():
    executor = FakeExecutor()
    loop = AgentLoop(NativeToolProvider(), tool_executor=executor)

    turn = loop.run("read README", "system")

    assert turn.final_response == "Read the file and found the answer."
    assert executor.calls == [("read_file", {"path": "README.md"}, "call_1")]
    assert turn.tool_calls_made[0].name == "read_file"


def test_agent_loop_executes_json_fallback_tool_calls():
    executor = FakeExecutor()
    provider = TextToolProvider(
        [
            '{"name": "read_file", "arguments": {"path": "README.md"}}',
            "Done after reading.",
        ]
    )
    loop = AgentLoop(provider, tool_executor=executor)

    turn = loop.run("read README", "system")

    assert turn.final_response == "Done after reading."
    assert executor.calls[0][0] == "read_file"
    assert executor.calls[0][1] == {"path": "README.md"}


def test_agent_loop_stops_at_max_iterations():
    executor = FakeExecutor()
    provider = TextToolProvider(
        [
            '{"name": "read_file", "arguments": {"path": "one.md"}}',
            '{"name": "read_file", "arguments": {"path": "two.md"}}',
        ]
    )
    loop = AgentLoop(provider, tool_executor=executor, max_iterations=2)

    turn = loop.run("keep reading", "system")

    assert turn.final_response == "[Agent loop reached maximum iterations without completing]"
    assert len(executor.calls) == 2


def test_agent_loop_detects_repeated_tool_calls():
    executor = FakeExecutor()
    provider = TextToolProvider(
        [
            '{"name": "read_file", "arguments": {"path": "same.md"}}',
            '{"name": "read_file", "arguments": {"path": "same.md"}}',
        ]
    )
    loop = AgentLoop(
        provider,
        tool_executor=executor,
        max_iterations=3,
        max_repeated_tool_calls=1,
    )

    turn = loop.run("repeat", "system")

    assert turn.final_response.startswith("[Agent loop stopped because")
    assert len(executor.calls) == 1
