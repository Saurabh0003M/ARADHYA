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

    def __call__(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> tuple[bool, bool]:
        ...


class CliConfirmationGate:
    """Interactive CLI confirmation using rich console."""

    def __call__(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> tuple[bool, bool]:
        from src.aradhya.ui.cli import render_tool_confirmation_prompt, prompt_input  # noqa: PLC0415

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

    def __call__(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> tuple[bool, bool]:
        return (False, False)


class TelegramConfirmationGate:
    """Telegram-based confirmation — sends a message and waits for reply.

    Uses a threading.Event to bridge between the sync confirmation gate
    protocol and Telegram's async message handling.  When a dangerous
    tool needs approval, this gate:

    1. Sends a formatted prompt to the user via Telegram.
    2. Blocks until the user replies "yes"/"y"/"approve" or the timeout
       expires (default 120 s).
    3. Returns (approved, persist=False).

    The Telegram channel must call ``receive_reply(text)`` when it gets
    a reply from the authorised chat.
    """

    def __init__(
        self,
        bot: Any = None,
        chat_id: int | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.bot = bot
        self.chat_id = chat_id
        self.timeout = timeout
        # Synchronisation primitives for async→sync bridging
        self._reply_event: Any = None   # threading.Event, created per call
        self._reply_text: str = ""

    def receive_reply(self, text: str) -> None:
        """Called by the Telegram channel when the user replies.

        This unblocks the waiting ``__call__`` method.
        """
        self._reply_text = text.strip().lower()
        if self._reply_event is not None:
            self._reply_event.set()

    def __call__(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> tuple[bool, bool]:
        if self.bot is None or self.chat_id is None:
            return (False, False)

        import threading
        from loguru import logger

        # Build a human-readable confirmation prompt
        arg_summary = "\n".join(
            f"  • {k}: {v!r}" for k, v in (arguments or {}).items()
        )
        prompt_text = (
            f"🔒 *Tool Confirmation Required*\n\n"
            f"Tool: `{tool_name}`\n"
            f"Arguments:\n{arg_summary}\n\n"
            f"Reply *yes* to approve or *no* to deny.\n"
            f"⏳ Auto-deny in {int(self.timeout)}s."
        )

        # Reset synchronisation state
        self._reply_event = threading.Event()
        self._reply_text = ""

        try:
            # Send confirmation prompt to user via Telegram
            self.bot.send_message(
                chat_id=self.chat_id,
                text=prompt_text,
                parse_mode="Markdown",
            )
        except Exception as exc:
            logger.warning(
                "Telegram gate: failed to send confirmation for '{}': {}",
                tool_name, exc,
            )
            return (False, False)

        # Block until user replies or timeout expires
        replied = self._reply_event.wait(timeout=self.timeout)
        self._reply_event = None

        if not replied:
            logger.info(
                "Telegram gate: confirmation for '{}' timed out after {}s",
                tool_name, self.timeout,
            )
            try:
                self.bot.send_message(
                    chat_id=self.chat_id,
                    text=f"⏰ Confirmation timed out for `{tool_name}` — denied.",
                    parse_mode="Markdown",
                )
            except Exception:
                pass
            return (False, False)

        approved = self._reply_text in ("y", "yes", "approve", "ok", "proceed")
        logger.info(
            "Telegram gate: user {} tool '{}' (reply: '{}')",
            "approved" if approved else "denied",
            tool_name,
            self._reply_text,
        )
        return (approved, False)
