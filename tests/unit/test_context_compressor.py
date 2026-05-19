"""Tests for the context compression module."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

# Mock loguru before imports
sys.modules["loguru"] = MagicMock()

from src.aradhya.context_compressor import (
    CompactionResult,
    TruncationPolicy,
    compact_history,
    estimate_messages_tokens,
    estimate_tokens,
    summarize_messages,
)


# ── Token estimation tests ────────────────────────────────────────────


def test_estimate_tokens_empty():
    assert estimate_tokens("") == 0


def test_estimate_tokens_short():
    # "Hello world" = 11 chars → ~3 tokens
    result = estimate_tokens("Hello world")
    assert 1 <= result <= 5


def test_estimate_tokens_long():
    text = "a" * 4000  # 4000 chars → ~1000 tokens
    result = estimate_tokens(text)
    assert 900 <= result <= 1100


def test_estimate_messages_tokens():
    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there, how can I help you today?"},
    ]
    result = estimate_messages_tokens(messages)
    assert result > 0
    # Each message has content tokens + ~4 overhead
    assert result > 8  # At least some tokens


# ── Summarization tests ──────────────────────────────────────────────


def test_summarize_messages_extractive():
    messages = [
        {"role": "user", "content": "Read the file main.py"},
        {"role": "assistant", "content": "Here is the content of main.py: ..."},
        {"role": "user", "content": "Now fix the bug on line 42"},
        {"role": "assistant", "content": "I've fixed the bug by changing..."},
    ]
    summary = summarize_messages(messages)
    assert "User topics:" in summary
    assert "Actions taken:" in summary


def test_summarize_messages_empty():
    summary = summarize_messages([])
    assert "compacted" in summary.lower()


def test_summarize_messages_with_model_summarizer():
    def mock_summarizer(messages):
        return "Custom LLM summary of the conversation."

    messages = [{"role": "user", "content": "hello"}]
    summary = summarize_messages(messages, model_summarizer=mock_summarizer)
    assert summary == "Custom LLM summary of the conversation."


def test_summarize_messages_model_failure_falls_back():
    def failing_summarizer(messages):
        raise RuntimeError("Model unavailable")

    messages = [
        {"role": "user", "content": "Hello there"},
        {"role": "assistant", "content": "Hi!"},
    ]
    summary = summarize_messages(messages, model_summarizer=failing_summarizer)
    # Should fall back to extractive summary
    assert "User topics:" in summary


# ── Compaction tests ──────────────────────────────────────────────────


def test_compact_history_no_compaction_needed():
    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi!"},
    ]
    policy = TruncationPolicy(mode="tokens", limit=10000)

    result_messages, result = compact_history(messages, policy=policy)

    assert result.compacted is False
    assert len(result_messages) == 2
    assert result_messages == messages


def test_compact_history_token_based():
    # Create a long conversation that exceeds token limit
    messages = []
    for i in range(30):
        messages.append({"role": "user", "content": f"User message {i} " + "x" * 200})
        messages.append({"role": "assistant", "content": f"Response {i} " + "y" * 200})

    # Set a low token limit to force compaction
    policy = TruncationPolicy(mode="tokens", limit=2000, min_keep=4, max_keep=10)

    result_messages, result = compact_history(messages, policy=policy)

    assert result.compacted is True
    assert result.original_messages == 60
    assert result.kept_messages <= 10
    assert result.summarized_messages > 0
    assert result.estimated_tokens_after < result.estimated_tokens_before

    # First message should be the summary
    assert result_messages[0]["role"] == "system"
    assert "[Compacted summary" in result_messages[0]["content"]

    # Recent messages should be preserved
    assert len(result_messages) > 1


def test_compact_history_message_based():
    messages = [
        {"role": "user", "content": f"Message {i}"}
        for i in range(20)
    ]
    policy = TruncationPolicy(mode="messages", limit=10, min_keep=4, max_keep=8)

    result_messages, result = compact_history(messages, policy=policy)

    assert result.compacted is True
    assert len(result_messages) <= 9  # 8 kept + 1 summary


def test_compact_history_preserves_min_keep():
    messages = [
        {"role": "user", "content": "x" * 1000}
        for _ in range(10)
    ]
    policy = TruncationPolicy(mode="tokens", limit=100, min_keep=6)

    result_messages, result = compact_history(messages, policy=policy)

    # Even with tiny token limit, should keep at least min_keep
    assert result.compacted is True
    assert result.kept_messages >= 6


def test_compact_history_too_few_messages():
    messages = [
        {"role": "user", "content": "Hello"},
    ]
    policy = TruncationPolicy(mode="tokens", limit=10, min_keep=6)

    result_messages, result = compact_history(messages, policy=policy)

    # Can't compact below min_keep
    assert result.compacted is False
    assert len(result_messages) == 1


def test_compact_history_default_policy():
    # Should work without explicit policy
    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi!"},
    ]

    result_messages, result = compact_history(messages)

    assert result.compacted is False
    assert len(result_messages) == 2


def test_compact_history_summary_content():
    messages = [
        {"role": "user", "content": "Read the config file"},
        {"role": "assistant", "content": "Here's the config: debug=true"},
        {"role": "user", "content": "Change debug to false"},
        {"role": "assistant", "content": "Done, updated the config."},
        {"role": "user", "content": "Now restart the server"},
        {"role": "assistant", "content": "Server restarted successfully."},
    ] + [
        {"role": "user", "content": f"Recent message {i}"}
        for i in range(10)
    ]

    policy = TruncationPolicy(mode="tokens", limit=500, min_keep=4, max_keep=6)
    result_messages, result = compact_history(messages, policy=policy)

    if result.compacted:
        summary = result_messages[0]["content"]
        assert "User topics:" in summary
