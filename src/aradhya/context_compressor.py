"""Token-aware context compression for the agent loop.

Implements Codex's truncation policy: when conversation history exceeds
a configurable token limit, older turns are summarized into a compact
``[Compacted]`` system message.  The most recent turns are preserved
at full fidelity for the model.

Token estimation uses a fast character-based heuristic (1 token ≈ 4 chars
for English text) to avoid heavy tokenizer dependencies.  This is
deliberately conservative — it's better to compact slightly early than
to overflow the context window.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loguru import logger

# ── Configuration ─────────────────────────────────────────────────────

# Approximate characters per token (conservative for English)
CHARS_PER_TOKEN = 4

# Default token budget for conversation history
DEFAULT_TOKEN_LIMIT = 8000

# Minimum number of recent messages to always keep at full fidelity
MIN_KEEP_MESSAGES = 6

# Maximum number of recent messages to keep
MAX_KEEP_MESSAGES = 20


@dataclass(frozen=True)
class TruncationPolicy:
    """Controls when and how context is compressed.

    Mirrors Codex's ``truncation_policy`` from session_meta.
    """

    mode: str = "tokens"  # "tokens" | "messages"
    limit: int = DEFAULT_TOKEN_LIMIT
    min_keep: int = MIN_KEEP_MESSAGES
    max_keep: int = MAX_KEEP_MESSAGES


@dataclass(frozen=True)
class CompactionResult:
    """Result of a context compaction operation."""

    compacted: bool
    original_messages: int
    kept_messages: int
    summarized_messages: int
    estimated_tokens_before: int
    estimated_tokens_after: int


# ── Token estimation ──────────────────────────────────────────────────


def estimate_tokens(text: str) -> int:
    """Estimate token count using character-based heuristic.

    This is intentionally conservative (overestimates slightly) to avoid
    context overflow.  For a proper implementation, swap this with a real
    tokenizer (tiktoken, sentencepiece, etc.).
    """
    if not text:
        return 0
    return max(1, len(text) // CHARS_PER_TOKEN)


def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    """Estimate total token count for a list of chat messages."""
    total = 0
    for msg in messages:
        # Each message has overhead: role token + content + separators
        content = msg.get("content", "") or ""
        total += estimate_tokens(content) + 4  # ~4 tokens overhead per message
    return total


# ── Summarization ─────────────────────────────────────────────────────


def summarize_messages(
    messages: list[dict[str, Any]],
    model_summarizer: Any = None,
) -> str:
    """Produce a compact summary of a batch of messages.

    If ``model_summarizer`` is provided, it is called with the messages
    to generate an LLM-powered summary.  Otherwise, falls back to a
    deterministic extraction of key user requests and assistant actions.
    """
    if model_summarizer is not None:
        try:
            return model_summarizer(messages)
        except Exception as error:
            logger.debug("Model summarizer failed, using fallback: {}", error)

    return _extractive_summary(messages)


def _extractive_summary(messages: list[dict[str, Any]]) -> str:
    """Fast, deterministic summary by extracting key content."""
    user_turns: list[str] = []
    assistant_turns: list[str] = []
    tool_names: set[str] = set()

    for msg in messages:
        role = msg.get("role", "")
        content = (msg.get("content", "") or "").strip()
        if not content:
            continue

        if role == "user":
            # Keep first 150 chars of each user message
            user_turns.append(content[:150])
        elif role == "assistant":
            # Keep first 100 chars of each assistant message
            assistant_turns.append(content[:100])
        elif role == "tool":
            # Extract tool name if present
            tool_call_id = msg.get("tool_call_id", "")
            if tool_call_id:
                tool_names.add(tool_call_id.split("_")[0] if "_" in tool_call_id else "tool")

    parts: list[str] = []

    if user_turns:
        # Summarize user requests
        topics = "; ".join(user_turns[-8:])  # Keep last 8 user turns
        parts.append(f"User topics: {topics}")

    if assistant_turns:
        # Summarize what was accomplished
        actions = "; ".join(assistant_turns[-5:])  # Keep last 5 assistant turns
        parts.append(f"Actions taken: {actions}")

    if tool_names:
        parts.append(f"Tools used: {', '.join(sorted(tool_names))}")

    if not parts:
        return "Previous conversation turns were compacted."

    return "\n".join(parts)


# ── Core compaction logic ─────────────────────────────────────────────


def compact_history(
    messages: list[dict[str, Any]],
    policy: TruncationPolicy | None = None,
    model_summarizer: Any = None,
) -> tuple[list[dict[str, Any]], CompactionResult]:
    """Compact a message history to fit within the token budget.

    Returns a tuple of (compacted_messages, result).

    The compaction algorithm:
    1. Estimate total tokens in the history.
    2. If under the limit, return the history unchanged.
    3. Otherwise, find the split point that keeps recent messages
       within budget while preserving at least ``min_keep`` messages.
    4. Summarize the older messages into a single system message.
    5. Return [summary] + recent_messages.
    """
    if policy is None:
        policy = TruncationPolicy()

    total_tokens = estimate_messages_tokens(messages)
    total_messages = len(messages)

    # Check if compaction is needed
    if policy.mode == "tokens":
        needs_compaction = total_tokens > policy.limit
    else:  # "messages" mode
        needs_compaction = total_messages > policy.limit

    if not needs_compaction or total_messages <= policy.min_keep:
        return messages, CompactionResult(
            compacted=False,
            original_messages=total_messages,
            kept_messages=total_messages,
            summarized_messages=0,
            estimated_tokens_before=total_tokens,
            estimated_tokens_after=total_tokens,
        )

    # Find the split point: keep as many recent messages as possible
    # while staying under budget (with room for the summary)
    summary_budget = 200  # Reserve ~200 tokens for the summary message
    remaining_budget = policy.limit - summary_budget

    # Start from the end and work backward
    keep_count = 0
    running_tokens = 0

    for i in range(total_messages - 1, -1, -1):
        msg_tokens = estimate_tokens(messages[i].get("content", "") or "") + 4
        if running_tokens + msg_tokens > remaining_budget:
            break
        running_tokens += msg_tokens
        keep_count += 1

    # Enforce min/max keep bounds
    keep_count = max(policy.min_keep, min(keep_count, policy.max_keep))
    keep_count = min(keep_count, total_messages)

    if keep_count >= total_messages:
        # Can't compact further
        return messages, CompactionResult(
            compacted=False,
            original_messages=total_messages,
            kept_messages=total_messages,
            summarized_messages=0,
            estimated_tokens_before=total_tokens,
            estimated_tokens_after=total_tokens,
        )

    # Split
    older_messages = messages[:-keep_count]
    recent_messages = messages[-keep_count:]

    # Generate summary
    summary_text = summarize_messages(older_messages, model_summarizer)
    summary_message = {
        "role": "system",
        "content": (
            f"[Compacted summary of {len(older_messages)} earlier messages]\n\n"
            f"{summary_text}"
        ),
    }

    compacted = [summary_message] + recent_messages
    after_tokens = estimate_messages_tokens(compacted)

    logger.info(
        "Context compacted: {} messages → {} ({}→{} est. tokens)",
        total_messages,
        len(compacted),
        total_tokens,
        after_tokens,
    )

    return compacted, CompactionResult(
        compacted=True,
        original_messages=total_messages,
        kept_messages=keep_count,
        summarized_messages=len(older_messages),
        estimated_tokens_before=total_tokens,
        estimated_tokens_after=after_tokens,
    )
