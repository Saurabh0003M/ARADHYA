"""Tests for Telegram allow-list auth — there is no trust-on-first-use."""
from __future__ import annotations

from unittest.mock import MagicMock

from src.aradhya.channels.telegram import AradhyaTelegramBot


def _bot(allowed):
    bot = AradhyaTelegramBot(token="test-token", allowed_user_ids=allowed)
    bot.api = MagicMock()  # never touch the network
    return bot


def test_allow_listed_user_is_permitted():
    bot = _bot([42])
    assert bot._is_allowed(42, "owner", chat_id=1) is True
    bot.api.send_message.assert_not_called()


def test_non_listed_user_is_denied():
    bot = _bot([42])
    assert bot._is_allowed(99, "stranger", chat_id=2) is False
    bot.api.send_message.assert_called_once()


def test_empty_allow_list_denies_without_auto_register():
    bot = _bot([])
    assert bot._is_allowed(7, "first", chat_id=3) is False
    # No trust-on-first-use: the user must NOT be added to the allow-list.
    assert 7 not in bot.allowed_user_ids
    # The bot replies with the sender's id so the owner can opt in.
    bot.api.send_message.assert_called_once()
    assert "7" in str(bot.api.send_message.call_args)
