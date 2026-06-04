with open('src/aradhya/agent_loop.py', 'r') as f:
    content = f.read()

# Helper code to replace run method and add helper methods
replacement = """    def run(
        self,
        user_message: str,
        system_prompt: str,
        history: list[dict[str, Any]] | None = None,
        thinking: ThinkingLevel = ThinkingLevel.MEDIUM,
        stream_handler: Callable[..., str] | None = None,
    ) -> AgentTurn:
        \"\"\"Execute a full agent turn.

        Returns an ``AgentTurn`` with the final response text and all
        intermediate tool calls/results.
        \"\"\"

        turn = AgentTurn(
            user_message=user_message,
            system_prompt=system_prompt,
            thinking_level=thinking,
        )

        messages = self._build_initial_messages(system_prompt, history, user_message)
        turn.messages = messages

        # Per-turn token accumulator — prevents single-turn context overflow
        # from accumulating huge tool outputs across many iterations.
        accumulated_result_tokens = 0

        for iteration in range(self.max_iterations):
            turn.iterations = iteration + 1

            try:
                response = self._call_model(messages, stream_handler=stream_handler)
            except Exception as error:
                logger.error("Agent loop model call failed: {}", error)
                turn.final_response = f"[Error calling model: {error}]"
                break

            # Check if model returned tool calls
            tool_calls = self._extract_tool_calls(response)

            if not tool_calls:
                # Model returned a final text response
                turn.final_response = self._extract_text(response)
                break

            # Execute tool calls
            for tool_call in tool_calls:
                if self._is_repeated_tool_call(turn.tool_calls_made, tool_call):
                    turn.final_response = (
                        "[Agent loop stopped because the model repeated the same "
                        f"tool call too many times: {tool_call.name}]"
                    )
                    logger.warning(
                        "Agent loop stopped on repeated tool call {} with args {}",
                        tool_call.name,
                        tool_call.arguments,
                    )
                    return turn

                turn.tool_calls_made.append(tool_call)

                if self.tool_executor is None:
                    result = ToolResult(
                        tool_call_id=tool_call.id,
                        name=tool_call.name,
                        output=f"[Tool '{tool_call.name}' not available — no executor configured]",
                        success=False,
                    )
                else:
                    result = self._execute_with_gate(tool_call)

                turn.tool_results.append(result)

                # ── Consecutive timeout kill switch (SWE-agent P1) ────
                if self._check_consecutive_timeouts(result.output, turn):
                    return turn

                # ── Per-turn token budget guard (Gap 3) ──────────────────
                accumulated_result_tokens, stop = self._handle_token_budget(
                    accumulated_result_tokens, result, tool_call, messages, turn
                )
                if stop:
                    return turn

                # Add tool call and result to message history
                self._append_tool_messages(messages, tool_call, result)
        else:
            turn.final_response = (
                "[Agent loop reached maximum iterations without completing]"
            )

        return turn

    def _build_initial_messages(
        self,
        system_prompt: str,
        history: list[dict[str, Any]] | None,
        user_message: str,
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})
        return messages

    def _check_consecutive_timeouts(self, output: str, turn: AgentTurn) -> bool:
        if output and ("timeout" in output.lower() or "timed out" in output.lower()):
            self._consecutive_timeouts += 1
            if self._consecutive_timeouts >= self.max_consecutive_timeouts:
                turn.final_response = (
                    f"[Agent loop killed after {self._consecutive_timeouts} "
                    f"consecutive command timeouts. The current approach is "
                    f"stuck. Try a completely different strategy.]"
                )
                logger.error(
                    "Kill switch: {} consecutive timeouts, aborting turn",
                    self._consecutive_timeouts,
                )
                return True
        else:
            self._consecutive_timeouts = 0
        return False

    def _handle_token_budget(
        self,
        accumulated_result_tokens: int,
        result: ToolResult,
        tool_call: ToolCall,
        messages: list[dict[str, Any]],
        turn: AgentTurn,
    ) -> tuple[int, bool]:
        result_tokens = max(1, len(result.output or "") // 4)
        accumulated_result_tokens += result_tokens
        if accumulated_result_tokens > self.turn_token_budget:
            logger.warning(
                "Turn token budget exceeded ({} > {}), injecting trim notice",
                accumulated_result_tokens,
                self.turn_token_budget,
            )
            # Add a trim notice so the model knows it hit the limit
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": tool_call.id,
                        "type": "function",
                        "function": {
                            "name": tool_call.name,
                            "arguments": json.dumps(tool_call.arguments),
                        },
                    }
                ],
            })
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": (
                    result.output[:500]
                    + f"\\n\\n[Output trimmed — turn token budget ({self.turn_token_budget} tokens) reached. "
                    "Summarize findings and respond now.]"
                ),
            })
            # Force one final model call to summarise
            try:
                final_resp = self._call_model(messages)
                turn.final_response = self._extract_text(final_resp)
            except Exception:
                turn.final_response = "[Tool results were trimmed due to token budget. Please ask a more focused question.]"
            return accumulated_result_tokens, True
        return accumulated_result_tokens, False

    def _append_tool_messages(
        self,
        messages: list[dict[str, Any]],
        tool_call: ToolCall,
        result: ToolResult,
    ) -> None:
        messages.append({
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.name,
                        "arguments": json.dumps(tool_call.arguments),
                    },
                }
            ],
        })
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": result.output,
        })"""

import re
# Find the start and end of the original run method
start_idx = content.find("    def run(")
end_idx = content.find("    def _call_model(")

if start_idx != -1 and end_idx != -1:
    new_content = content[:start_idx] + replacement + "\n\n" + content[end_idx:]
    with open('src/aradhya/agent_loop.py', 'w') as f:
        f.write(new_content)
    print("Replaced run method and added helpers.")
else:
    print("Could not find boundaries for replacement.")
