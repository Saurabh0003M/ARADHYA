"""Channel-aware confirmation gate protocol.

Replaces the hardcoded ``_cli_gate`` closure with a typed protocol
that supports multiple channels (CLI, Telegram, daemon/headless).

Usage::

    gate = CliConfirmationGate()
    # or
    gate = TelegramConfirmationGate(bot)
    # or
    gate = HeadlessConfirmationGate()  # always denies

    loop = AgentLoop(..., confirmation_gate=gate)
"""

from __future__ import annotations

from typing import Any, Protocol


class ConfirmationResult:
    """Result of a confirmation prompt."""

    __slots__ = ("approved", "persist")

    def __init__(self, approved: bool, persist: bool = False) -> None:
        self.approved = approved
        self.persist = persist

    def as_tuple(self) -> tuple[bool, bool]:
        return (self.approved, self.persist)


class ConfirmationGate(Protocol):
    """Protocol for channel-agnostic confirmation gates.

    The agent loop calls this with a tool name and arguments.
    The implementation prompts the user through whatever channel
    is appropriate (CLI, Telegram, web UI, etc.).

    Returns (approved: bool, persist: bool).
    """

    def __call__(self, tool_name: str, arguments: dict[str, Any]) -> tuple[bool, bool]: ...


class CliConfirmationGate:
    """Interactive CLI confirmation using rich console."""

    def __call__(self, tool_name: str, arguments: dict[str, Any]) -> tuple[bool, bool]:
        from src.aradhya.ui.cli import (  # pylint: disable=import-outside-toplevel
            render_tool_confirmation_prompt,
            prompt_input,
        )  # noqa: PLC0415

        render_tool_confirmation_prompt(tool_name, arguments)
        try:
            answer = prompt_input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            return (False, False)
        if answer in ("y", "yes"):
            return (True, False)
        if answer in ("a", "always"):
            return (True, True)
        return (False, False)


class HeadlessConfirmationGate:
    """Headless / daemon mode — always denies dangerous tools.

    Use this when there is no interactive user to prompt.
    """

    def __call__(self, tool_name: str, arguments: dict[str, Any]) -> tuple[bool, bool]:
        return (False, False)


class TelegramConfirmationGate:
    """Telegram-based confirmation (sends message, waits for reply).

    Requires the Telegram bot instance to send/receive messages.
    This is a stub — wire to actual bot.send_message + wait_for_reply
    when integrating with telegram_bot.py.
    """

    def __init__(self, bot: Any = None, chat_id: int | None = None) -> None:
        self.bot = bot
        self.chat_id = chat_id

    def __call__(self, tool_name: str, arguments: dict[str, Any]) -> tuple[bool, bool]:
        if self.bot is None or self.chat_id is None:
            return (False, False)

        try:
            # This would need async/sync bridge in real implementation
            # For now, deny in Telegram mode (safe default)
            from loguru import logger  # pylint: disable=import-outside-toplevel

            logger.warning(
                "Telegram gate: tool '{}' requires confirmation but "
                "async Telegram approval is not yet wired. Denying.",
                tool_name,
            )
            return (False, False)
        except Exception:
            return (False, False)
