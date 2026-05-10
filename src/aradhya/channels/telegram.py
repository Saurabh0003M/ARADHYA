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
from pathlib import Path
from typing import Any

from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parents[2]

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
    - If the allow list is empty, the first user to message gets
      auto-registered and a warning is logged.
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
        self._auto_registered = False

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
        response = self._process_message(text)
        self.api.send_message(chat_id, response)

    def _is_allowed(self, user_id: int, user_name: str, chat_id: int) -> bool:
        """Check if user is in the allow list. Auto-register first user if empty."""
        if user_id in self.allowed_user_ids:
            return True

        if not self.allowed_user_ids and not self._auto_registered:
            self.allowed_user_ids.add(user_id)
            self._auto_registered = True
            logger.warning(
                "Auto-registered first Telegram user: {} (ID: {}). "
                "Add this ID to profile.json telegram.allowed_user_ids "
                "for persistent access.",
                user_name, user_id,
            )
            self.api.send_message(
                chat_id,
                f"Welcome {user_name}! You've been auto-registered.\n\n"
                f"Your user ID is `{user_id}`. Add it to "
                f"`profile.json` under `telegram.allowed_user_ids` "
                f"for persistent access.",
            )
            return True

        logger.warning("Unauthorized Telegram user: {} (ID: {})", user_name, user_id)
        self.api.send_message(
            chat_id,
            "Sorry, you're not authorized to use this bot.\n"
            "Ask the bot owner to add your user ID to the allow list.",
        )
        return False

    def _process_message(self, text: str) -> str:
        """Route a message through the Aradhya assistant."""
        if self.assistant is None:
            return (
                "Aradhya assistant is not connected. "
                "Start the bot via the main CLI for full functionality."
            )

        try:
            # Ensure assistant is awake
            if not self.assistant.state.is_awake:
                from src.aradhya.assistant_models import WakeSource
                self.assistant.handle_wake(WakeSource.FLOATING_ICON)

            response = self.assistant.handle_transcript(text)

            parts = []
            if response.transcript_echo:
                parts.append(f"_Heard: {response.transcript_echo}_")
            parts.append(response.spoken_response)

            if response.awaiting_confirmation:
                parts.append(
                    "\n-- Reply 'yes proceed' to execute, or 'cancel' to discard."
                )

            return "\n".join(parts)

        except Exception as error:
            logger.error("Telegram message processing failed: {}", error)
            return f"Error processing your request: {error}"

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

    print(f"Aradhya Telegram bot starting...")
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
