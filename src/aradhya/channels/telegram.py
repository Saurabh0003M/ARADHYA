"""Telegram bot interface for remote Aradhya access.

Run standalone:  python -m src.aradhya.telegram_bot

Or integrate with the main CLI by setting the ARADHYA_TELEGRAM_TOKEN
environment variable or adding it to profile.json under
``telegram.bot_token``.

Setup:
1. Message @BotFather on Telegram
2. Create a new bot with /newbot
3. Copy the token
4. Set ARADHYA_TELEGRAM_TOKEN=<token> in your environment
   or add to profile.json: {"telegram": {"bot_token": "...", "allowed_user_ids": []}}
5. Start: python -m src.aradhya.telegram_bot
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any

from loguru import logger

from src.aradhya.paths import get_project_root
from src.aradhya.confirmation_gates import HeadlessConfirmationGate

PROJECT_ROOT = get_project_root()

# ── Configuration ─────────────────────────────────────────────────────

def _load_telegram_config() -> dict[str, Any]:
    """Load Telegram config from profile.json or environment."""
    config: dict[str, Any] = {
        "bot_token": "",
        "allowed_user_ids": [],
        "polling_interval": 1,
    }

    # Try environment variable first
    env_token = os.environ.get("ARADHYA_TELEGRAM_TOKEN", "")
    if env_token:
        config["bot_token"] = env_token

    env_users = os.environ.get("ARADHYA_TELEGRAM_USERS", "")
    if env_users:
        config["allowed_user_ids"] = [
            int(uid.strip()) for uid in env_users.split(",") if uid.strip()
        ]

    # Try profile.json
    profile_path = PROJECT_ROOT / "core" / "memory" / "profile.json"
    if profile_path.is_file():
        try:
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            tg = profile.get("telegram", {})
            if not config["bot_token"] and tg.get("bot_token"):
                config["bot_token"] = tg["bot_token"]
            if not config["allowed_user_ids"] and tg.get("allowed_user_ids"):
                config["allowed_user_ids"] = tg["allowed_user_ids"]
        except (json.JSONDecodeError, OSError):
            pass

    return config


# ── Telegram API (requests-based, no extra deps) ─────────────────────

class TelegramAPI:
    """Minimal Telegram Bot API wrapper using only ``requests``."""

    def __init__(self, token: str) -> None:
        self.base_url = f"https://api.telegram.org/bot{token}"
        self._offset = 0

    def _call(self, method: str, **params) -> dict[str, Any]:
        import requests
        resp = requests.post(
            f"{self.base_url}/{method}",
            json={k: v for k, v in params.items() if v is not None},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram API error: {data}")
        return data.get("result", {})

    def get_me(self) -> dict:
        return self._call("getMe")

    def get_updates(self, timeout: int = 20) -> list[dict]:
        updates = self._call(
            "getUpdates",
            offset=self._offset,
            timeout=timeout,
            allowed_updates=["message"],
        )
        if updates:
            self._offset = updates[-1]["update_id"] + 1
        return updates

    def send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: str = "Markdown",
    ) -> dict:
        # Telegram has a 4096 char limit per message
        if len(text) > 4000:
            text = text[:3997] + "..."
        try:
            return self._call(
                "sendMessage",
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
            )
        except Exception:
            # Fallback without markdown if parsing fails
            return self._call(
                "sendMessage",
                chat_id=chat_id,
                text=text,
                parse_mode=None,
            )

    def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        parse_mode: str = "Markdown",
    ) -> dict:
        if len(text) > 4000:
            text = text[:3997] + "..."
        try:
            return self._call(
                "editMessageText",
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode=parse_mode,
            )
        except Exception:
            return self._call(
                "editMessageText",
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode=None,
            )

    def send_typing(self, chat_id: int) -> None:
        try:
            self._call("sendChatAction", chat_id=chat_id, action="typing")
        except Exception:
            pass


# ── Bot logic ─────────────────────────────────────────────────────────

class AradhyaTelegramBot:
    """Telegram bot that connects to the Aradhya assistant.

    Messages from allowed users are routed through the assistant's
    ``handle_transcript`` method. Responses are sent back as Telegram
    messages.

    Security:
    - Only messages from ``allowed_user_ids`` are processed.
    - There is NO trust-on-first-use: an empty allow-list denies everyone and
      replies with the sender's user ID so the owner can opt them in.
    """

    def __init__(
        self,
        token: str,
        allowed_user_ids: list[int] | None = None,
        assistant: Any = None,
    ) -> None:
        self.api = TelegramAPI(token)
        self.allowed_user_ids: set[int] = set(allowed_user_ids or [])
        self.assistant = assistant
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the bot in a background thread."""
        if self._running:
            return

        # Verify token
        me = self.api.get_me()
        bot_name = me.get("username", "unknown")
        logger.info("Telegram bot started as @{}", bot_name)

        self._running = True
        self._thread = threading.Thread(
            target=self._poll_loop, daemon=True, name="aradhya-telegram",
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the bot."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("Telegram bot stopped")

    def is_running(self) -> bool:
        return self._running

    def _poll_loop(self) -> None:
        """Long-poll Telegram for new messages."""
        while self._running:
            try:
                updates = self.api.get_updates(timeout=20)
                for update in updates:
                    self._handle_update(update)
            except KeyboardInterrupt:
                break
            except Exception as error:
                logger.error("Telegram poll error: {}", error)
                time.sleep(5)

    def _handle_update(self, update: dict) -> None:
        """Process a single Telegram update."""
        message = update.get("message")
        if not message:
            return

        chat_id = message["chat"]["id"]
        user_id = message.get("from", {}).get("id", 0)
        user_name = message.get("from", {}).get("first_name", "Unknown")
        text = message.get("text", "").strip()

        if not text:
            return

        # Security: check allowed users
        if not self._is_allowed(user_id, user_name, chat_id):
            return

        logger.info("Telegram message from {} ({}): {}", user_name, user_id, text[:100])

        # Handle special commands
        if text == "/start":
            self.api.send_message(
                chat_id,
                "Hello! I'm *Aradhya*, your personal AI assistant.\n\n"
                "Just send me a message and I'll help you.\n\n"
                "Commands:\n"
                "/status - System status\n"
                "/help - Available commands\n"
                "/skills - List loaded skills",
            )
            return

        if text == "/status":
            self._send_status(chat_id)
            return

        if text == "/help":
            self.api.send_message(
                chat_id,
                "*Aradhya Remote*\n\n"
                "Just type naturally -- I understand plain English.\n\n"
                "/status - System status\n"
                "/skills - Loaded skills\n"
                "/help - This message",
            )
            return

        if text == "/skills":
            self._send_skills(chat_id)
            return

        # Route through assistant
        self.api.send_typing(chat_id)
        self._process_message(chat_id, text)

    def _is_allowed(self, user_id: int, user_name: str, chat_id: int) -> bool:
        """Return True only for explicitly allow-listed users.

        Security: there is deliberately NO trust-on-first-use auto-registration.
        A Telegram bot token is not a strong secret, so auto-granting the first
        messager would hand assistant control to anyone who discovers the bot.
        The owner must add their numeric user ID to ``telegram.allowed_user_ids``
        in profile.json (or the ``ARADHYA_TELEGRAM_USERS`` env var). When the
        allow-list is empty, the bot replies with the sender's ID to opt in.
        """
        if user_id in self.allowed_user_ids:
            return True

        if not self.allowed_user_ids:
            logger.warning(
                "Telegram allow-list is empty; denying user {} (ID: {}). Add this "
                "ID to telegram.allowed_user_ids in profile.json (or the "
                "ARADHYA_TELEGRAM_USERS env var) to grant access.",
                user_name, user_id,
            )
            self.api.send_message(
                chat_id,
                f"This bot has no authorized users configured yet.\n\n"
                f"Your user ID is `{user_id}`. The bot owner must add it to "
                f"`telegram.allowed_user_ids` in profile.json (or the "
                f"`ARADHYA_TELEGRAM_USERS` env var) to grant access.",
            )
            return False

        logger.warning("Unauthorized Telegram user: {} (ID: {})", user_name, user_id)
        self.api.send_message(
            chat_id,
            "Sorry, you're not authorized to use this bot.\n"
            "Ask the bot owner to add your user ID to the allow list.",
        )
        return False

    def _wake_assistant(self) -> None:
        """Ensure the assistant is awake before processing."""
        if self.assistant is not None and not self.assistant.state.is_awake:
            from src.aradhya.assistant_models import WakeSource
            self.assistant.handle_wake(WakeSource.FLOATING_ICON)

    def _build_final_text(self, response: Any, accumulated_text: str) -> str:
        """Construct the final message text from the assistant response."""
        parts = []
        if response.transcript_echo:
            parts.append(f"_Heard: {response.transcript_echo}_")

        # The full response might have formatting stripped or clean tags, use it over raw accumulation
        if response.spoken_response:
            parts.append(response.spoken_response)
        elif accumulated_text:
            parts.append(accumulated_text)

        if response.awaiting_confirmation:
            parts.append(
                "\n-- Reply 'yes proceed' to execute, or 'cancel' to discard."
            )

        return "\n".join(parts)

    def _deliver_final_text(self, chat_id: int, msg_id: int | None, final_text: str) -> None:
        """Deliver the final text either by editing the placeholder or sending anew."""
        if msg_id:
            try:
                self.api.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=final_text,
                )
            except Exception:
                self.api.send_message(chat_id, final_text)
        else:
            self.api.send_message(chat_id, final_text)

    def _process_message(self, chat_id: int, text: str) -> None:
        """Route a message through the Aradhya assistant with live streaming."""
        if self.assistant is None:
            self.api.send_message(
                chat_id,
                "Aradhya assistant is not connected. Start the bot via the main CLI."
            )
            return

        try:
            self._wake_assistant()

            # Send a placeholder message
            placeholder = self.api.send_message(chat_id, "🤔 *Thinking...*")
            msg_id = placeholder.get("message_id")

            accumulated_text = ""
            last_edit_time = 0.0
            edit_interval = 1.5  # Prevent Telegram rate limits (1 edit per sec max)

            def stream_handler(chunk: str):
                nonlocal accumulated_text, last_edit_time
                accumulated_text += chunk

                now = time.time()
                if now - last_edit_time > edit_interval and msg_id:
                    try:
                        self.api.edit_message_text(
                            chat_id=chat_id,
                            message_id=msg_id,
                            text=accumulated_text + " ⏳",
                        )
                        last_edit_time = now
                    except Exception as e:
                        logger.debug("Telegram stream edit failed: {}", e)

            # Remote channel: deny dangerous tools. Interactive Telegram approval
            # is a follow-up — it needs the bot to process messages on worker
            # threads so a blocking gate cannot deadlock the single poll loop.
            response = self.assistant.handle_transcript(
                text,
                stream_handler=stream_handler,
                confirmation_gate=HeadlessConfirmationGate(),
            )

            final_text = self._build_final_text(response, accumulated_text)
            self._deliver_final_text(chat_id, msg_id, final_text)

        except Exception as error:
            logger.error("Telegram message processing failed: {}", error)
            self.api.send_message(chat_id, f"Error processing your request: {error}")

    def _send_status(self, chat_id: int) -> None:
        """Send system status."""
        if self.assistant is None:
            self.api.send_message(chat_id, "Assistant not connected.")
            return

        state = "Awake" if self.assistant.state.is_awake else "Idle"
        pending = "Yes" if self.assistant.state.pending_plan else "None"
        skills_count = (
            self.assistant.skill_registry.active_count
            if self.assistant.skill_registry else 0
        )

        self.api.send_message(
            chat_id,
            f"*Aradhya Status*\n\n"
            f"State: {state}\n"
            f"Pending plan: {pending}\n"
            f"Active skills: {skills_count}\n"
            f"Live execution: {'Enabled' if self.assistant.preferences.allow_live_execution else 'Dry-run'}",
        )

    def _send_skills(self, chat_id: int) -> None:
        """Send skills list."""
        if self.assistant is None or self.assistant.skill_registry is None:
            self.api.send_message(chat_id, "No skills loaded.")
            return

        skills = self.assistant.skill_registry.all_skills()
        if not skills:
            self.api.send_message(chat_id, "No skills loaded.")
            return

        lines = ["*Loaded Skills*\n"]
        for skill in skills:
            status = "ON" if skill.enabled else "OFF"
            lines.append(f"[{status}] {skill.name} -- {skill.description}")

        self.api.send_message(chat_id, "\n".join(lines))


# ── Standalone entry point ────────────────────────────────────────────

def main() -> None:
    """Run the Telegram bot standalone with a full assistant."""
    config = _load_telegram_config()

    if not config["bot_token"]:
        print("Error: No Telegram bot token configured.")
        print()
        print("Set it via:")
        print("  1. Environment: ARADHYA_TELEGRAM_TOKEN=<token>")
        print("  2. profile.json: {\"telegram\": {\"bot_token\": \"<token>\"}}")
        print()
        print("Get a token from @BotFather on Telegram.")
        return

    # Build full assistant for standalone mode
    from src.aradhya.assistant_core import AradhyaAssistant
    from src.aradhya.model_provider import build_text_model_provider
    from src.aradhya.model_setup import bootstrap_runtime_profile
    from src.aradhya.runtime_profile import load_runtime_profile
    from src.aradhya.skills import load_skills

    runtime_profile = load_runtime_profile(PROJECT_ROOT)
    runtime_profile = bootstrap_runtime_profile(runtime_profile, PROJECT_ROOT)
    model_provider = build_text_model_provider(runtime_profile.model)
    skill_registry = load_skills(PROJECT_ROOT)
    assistant = AradhyaAssistant.from_project_root(
        PROJECT_ROOT,
        model_provider=model_provider,
        skill_registry=skill_registry,
    )
    # Auto-wake
    assistant.state.is_awake = True

    bot = AradhyaTelegramBot(
        token=config["bot_token"],
        allowed_user_ids=config.get("allowed_user_ids", []),
        assistant=assistant,
    )

    print("Aradhya Telegram bot starting...")
    print(f"Allowed users: {config.get('allowed_user_ids', []) or 'auto-register first user'}")
    print("Press Ctrl+C to stop.")
    print()

    bot.start()

    try:
        while bot.is_running():
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
        bot.stop()


if __name__ == "__main__":
    main()
