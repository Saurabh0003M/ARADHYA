"""Pluggable history processor pipeline for context compression.

Inspired by SWE-agent's history_processors, this module provides a chain
of transformations that compress conversation history before sending it
to the model.  Each processor takes a list of messages and returns a
(potentially smaller) list.

Processors are applied in order::

    messages -> LastNObservations -> ClosedWindowProcessor
             -> OutputTruncator -> RegexScrubber -> compressed messages

Key insight from SWE-agent: instead of naively dropping entire messages,
**replace** old tool outputs with short summaries like
"(42 lines omitted)" — the model retains awareness that a step happened
while freeing context space.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Protocol

from loguru import logger


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

class HistoryProcessor(Protocol):
    """A single transformation over a message list."""

    def __call__(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ...


# ---------------------------------------------------------------------------
# Processors
# ---------------------------------------------------------------------------

@dataclass
class LastNToolOutputs:
    """Keep only the last *n* tool-result messages in full.

    Older tool results are replaced with a summary line showing how many
    lines were elided.  Non-tool messages (system, user, assistant) are
    always kept.

    This is the single highest-impact processor — on long sessions it can
    compress history 10x while keeping the model aware of all steps.
    """

    n: int = 5

    def __call__(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # Find indices of tool-result messages
        tool_indices = [
            i for i, m in enumerate(messages)
            if m.get("role") == "tool" or m.get("message_type") == "tool_result"
        ]

        if len(tool_indices) <= self.n:
            return messages  # nothing to elide

        # Keep the last N tool results; elide older ones
        # Never elide the first tool result (often the setup context)
        keep_set = set(tool_indices[-self.n:])
        if tool_indices:
            keep_set.add(tool_indices[0])

        result = []
        for i, msg in enumerate(messages):
            if i in tool_indices and i not in keep_set:
                content = msg.get("content", "")
                n_lines = content.count("\n") + 1 if content else 0
                n_chars = len(content)
                result.append({
                    **msg,
                    "content": (
                        f"[Previous tool output: {n_lines} lines, "
                        f"{n_chars} chars omitted]"
                    ),
                    "_elided": True,
                })
            else:
                result.append(msg)
        return result


@dataclass
class OutputTruncator:
    """Truncate individual message content that exceeds a character limit.

    Unlike naive truncation, this tells the model exactly what happened
    and suggests remedies (use head/tail/grep).
    """

    max_chars: int = 8000
    template: str = (
        "{truncated_content}\n\n"
        "[Output truncated: {elided_chars} of {total_chars} characters removed. "
        "Try using head/tail/grep for specific output, "
        "or redirect to a file with > output.txt]"
    )

    def __call__(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = []
        for msg in messages:
            content = msg.get("content", "")
            if len(content) > self.max_chars:
                truncated = self.template.format(
                    truncated_content=content[:self.max_chars],
                    elided_chars=len(content) - self.max_chars,
                    total_chars=len(content),
                )
                result.append({**msg, "content": truncated, "_truncated": True})
            else:
                result.append(msg)
        return result


@dataclass
class ClosedWindowProcessor:
    """Deduplicate file views — keep only the latest view of each file.

    When the agent views the same file multiple times (common with
    iterative editing), older views are replaced with a summary.

    Detects file views by looking for path-like strings in tool calls
    or content matching common patterns like:
        ``[File: path/to/file.py (123 lines total)]``
        ``read_file(path="...")``
    """

    # Matches patterns like [File: some/path.py (N lines total)]
    _file_pattern: re.Pattern = field(
        default_factory=lambda: re.compile(
            r"\[File:\s+(.+?)\s+\(\d+\s+lines?\s+total\)\]"
        ),
        repr=False,
    )

    # Matches path= or file_path= in tool arguments
    _arg_pattern: re.Pattern = field(
        default_factory=lambda: re.compile(
            r'(?:path|file_path)\s*[=:]\s*["\']?([^"\'}\s,]+)'
        ),
        repr=False,
    )

    def _extract_file_path(self, msg: dict[str, Any]) -> str | None:
        """Try to extract a file path from a message."""
        content = msg.get("content", "")
        # Check content for file view patterns
        match = self._file_pattern.search(content)
        if match:
            return match.group(1)
        # Check for path arguments
        match = self._arg_pattern.search(content)
        if match:
            return match.group(1)
        return None

    def __call__(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # Walk backwards to find the LATEST view of each file
        latest_views: dict[str, int] = {}  # filepath -> last index
        for i in range(len(messages) - 1, -1, -1):
            path = self._extract_file_path(messages[i])
            if path and path not in latest_views:
                latest_views[path] = i

        # Now walk forward and elide non-latest file views
        result = []
        for i, msg in enumerate(messages):
            path = self._extract_file_path(msg)
            if path and path in latest_views and latest_views[path] != i:
                content = msg.get("content", "")
                n_lines = content.count("\n") + 1
                result.append({
                    **msg,
                    "content": (
                        f"[Outdated file view of {path}: {n_lines} lines omitted. "
                        f"See latest view below.]"
                    ),
                    "_deduped": True,
                })
            else:
                result.append(msg)
        return result


@dataclass
class RegexScrubber:
    """Remove or redact content matching regex patterns.

    Useful for:
    - Stripping API keys that leaked into outputs
    - Removing verbose debug output
    - Clearing long diff blocks from history
    """

    patterns: list[str] = field(default_factory=lambda: [
        # Common API key patterns
        r"(?:api[_-]?key|token|secret|password)\s*[=:]\s*['\"][^'\"]{8,}['\"]",
        # Very long hex strings (likely hashes/tokens)
        r"\b[0-9a-fA-F]{40,}\b",
    ])
    replacement: str = "[REDACTED]"

    def __call__(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        compiled = [re.compile(p, re.IGNORECASE) for p in self.patterns]
        result = []
        for msg in messages:
            content = msg.get("content", "")
            modified = content
            for pattern in compiled:
                modified = pattern.sub(self.replacement, modified)
            if modified != content:
                result.append({**msg, "content": modified, "_scrubbed": True})
            else:
                result.append(msg)
        return result


@dataclass
class ConsecutiveTimeoutTracker:
    """Track consecutive tool timeouts and inject warnings.

    After N consecutive timeouts, injects a system message telling the
    model to try a different approach.
    """

    max_consecutive: int = 3
    _consecutive_count: int = field(default=0, repr=False)

    def __call__(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        self._consecutive_count = 0
        for msg in messages:
            content = msg.get("content", "")
            if ("timeout" in content.lower() or "timed out" in content.lower()) and (
                msg.get("role") == "tool"
                or msg.get("message_type") == "tool_result"
            ):
                self._consecutive_count += 1
            else:
                if msg.get("role") == "tool" or msg.get("message_type") == "tool_result":
                    self._consecutive_count = 0

        result = list(messages)
        if self._consecutive_count >= self.max_consecutive:
            result.append({
                "role": "system",
                "content": (
                    f"[WARNING: {self._consecutive_count} consecutive command timeouts. "
                    f"The current approach is likely stuck. Try a completely different "
                    f"strategy — shorter commands, different tools, or break the "
                    f"problem into smaller steps.]"
                ),
                "message_type": "system_warning",
            })
        return result


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

@dataclass
class HistoryProcessorPipeline:
    """Chain multiple processors into a single pass.

    Usage::

        pipeline = HistoryProcessorPipeline(processors=[
            LastNToolOutputs(n=5),
            ClosedWindowProcessor(),
            OutputTruncator(max_chars=8000),
            RegexScrubber(),
            ConsecutiveTimeoutTracker(),
        ])

        compressed = pipeline(messages)
    """

    processors: list[HistoryProcessor] = field(default_factory=list)

    def __call__(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = messages
        for processor in self.processors:
            before = len(result)
            result = processor(result)
            # Calculate compression stats
            after_chars = sum(len(m.get("content", "")) for m in result)
            before_chars = sum(len(m.get("content", "")) for m in messages)
            if before != len(result):
                logger.debug(
                    "History processor {}: {} -> {} messages",
                    type(processor).__name__,
                    before,
                    len(result),
                )
        return result

    def add(self, processor: HistoryProcessor) -> "HistoryProcessorPipeline":
        """Fluent API for adding processors."""
        self.processors.append(processor)
        return self


def default_pipeline() -> HistoryProcessorPipeline:
    """Create the default ARADHYA history processing pipeline."""
    return HistoryProcessorPipeline(processors=[
        LastNToolOutputs(n=5),
        ClosedWindowProcessor(),
        OutputTruncator(max_chars=8000),
        RegexScrubber(),
        ConsecutiveTimeoutTracker(),
    ])
