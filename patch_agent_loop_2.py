with open('src/aradhya/agent_loop.py', 'r') as f:
    content = f.read()

# I want to further extract the inner loop body into `_process_tool_call`
# So run looks like this:

run_replacement = """    def run(
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
                accumulated_result_tokens, stop = self._process_tool_call(
                    tool_call, turn, messages, accumulated_result_tokens
                )
                if stop:
                    return turn
        else:
            turn.final_response = (
                "[Agent loop reached maximum iterations without completing]"
            )

        return turn"""

process_tool_call_def = """    def _process_tool_call(
        self,
        tool_call: ToolCall,
        turn: AgentTurn,
        messages: list[dict[str, Any]],
        accumulated_result_tokens: int,
    ) -> tuple[int, bool]:
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
            return accumulated_result_tokens, True

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
            return accumulated_result_tokens, True

        # ── Per-turn token budget guard (Gap 3) ──────────────────
        accumulated_result_tokens, stop = self._handle_token_budget(
            accumulated_result_tokens, result, tool_call, messages, turn
        )
        if stop:
            return accumulated_result_tokens, True

        # Add tool call and result to message history
        self._append_tool_messages(messages, tool_call, result)
        return accumulated_result_tokens, False"""

start_idx = content.find("    def run(")
end_idx = content.find("    def _build_initial_messages(")

if start_idx != -1 and end_idx != -1:
    new_content = content[:start_idx] + run_replacement + "\n\n" + process_tool_call_def + "\n\n" + content[end_idx:]
    with open('src/aradhya/agent_loop.py', 'w') as f:
        f.write(new_content)
    print("Replaced run method and added process_tool_call.")
else:
    print("Could not find boundaries for replacement.")
