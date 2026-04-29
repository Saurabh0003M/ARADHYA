"""Self-improvement learnings engine.

Inspired by ClawHub's ``self-improving-agent`` skill, this module provides
a structured logging system for errors, corrections, and learnings that
occur during agent execution.  When patterns recur (≥3 times), they are
automatically promoted to ``rules.md`` so the agent permanently remembers.

Storage layout:
    core/memory/.learnings/
        ERRORS.md       — tool failures, command errors
        LEARNINGS.md    — corrections, insights, best practices
        FEATURES.md     — user-requested capabilities
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from loguru import logger

from src.aradhya.tools.tool_registry import tool_definition

_PROMOTION_THRESHOLD = 3  # Promote to rules.md after this many occurrences


class LearningsEngine:
    """Manages the .learnings/ directory and its log files."""

    def __init__(self, project_root: Path) -> None:
        self.learnings_dir = project_root / "core" / "memory" / ".learnings"
        self.rules_file = project_root / "core" / "memory" / "user_context" / "rules.md"
        self._ensure_files()

    def _ensure_files(self) -> None:
        """Create the learnings directory and files if they don't exist."""
        self.learnings_dir.mkdir(parents=True, exist_ok=True)

        for filename, header in [
            ("ERRORS.md", "# Errors\n\nCommand failures and integration errors.\n\n---\n"),
            ("LEARNINGS.md", "# Learnings\n\nCorrections, insights, and best practices.\n\n---\n"),
            ("FEATURES.md", "# Feature Requests\n\nCapabilities requested by the user.\n\n---\n"),
        ]:
            path = self.learnings_dir / filename
            if not path.is_file():
                path.write_text(header, encoding="utf-8")

    def log_error(
        self,
        tool_name: str,
        error_message: str,
        context: str = "",
    ) -> str:
        """Log a tool execution error."""
        entry_id = self._generate_id("ERR")
        stamp = datetime.now().isoformat(timespec="seconds")

        entry = (
            f"\n## [{entry_id}] {tool_name}\n"
            f"**Logged**: {stamp}\n"
            f"**Priority**: high\n"
            f"**Status**: pending\n\n"
            f"### Error\n{error_message}\n"
        )
        if context:
            entry += f"\n### Context\n{context}\n"
        entry += "\n---\n"

        self._append("ERRORS.md", entry)
        logger.info("Logged error {}: {}", entry_id, error_message[:100])
        return entry_id

    def log_learning(
        self,
        category: str,
        summary: str,
        details: str = "",
        priority: str = "medium",
    ) -> str:
        """Log a learning (correction, insight, best practice, knowledge gap)."""
        entry_id = self._generate_id("LRN")
        stamp = datetime.now().isoformat(timespec="seconds")

        entry = (
            f"\n## [{entry_id}] {category}\n"
            f"**Logged**: {stamp}\n"
            f"**Priority**: {priority}\n"
            f"**Status**: pending\n\n"
            f"### Summary\n{summary}\n"
        )
        if details:
            entry += f"\n### Details\n{details}\n"
        entry += "\n---\n"

        self._append("LEARNINGS.md", entry)
        logger.info("Logged learning {}: {}", entry_id, summary[:100])

        # Check for promotion
        self._check_promotion(summary)

        return entry_id

    def log_feature_request(
        self,
        capability: str,
        user_context: str = "",
    ) -> str:
        """Log a user-requested feature/capability."""
        entry_id = self._generate_id("FEAT")
        stamp = datetime.now().isoformat(timespec="seconds")

        entry = (
            f"\n## [{entry_id}] {capability}\n"
            f"**Logged**: {stamp}\n"
            f"**Priority**: medium\n"
            f"**Status**: pending\n\n"
            f"### Requested Capability\n{capability}\n"
        )
        if user_context:
            entry += f"\n### User Context\n{user_context}\n"
        entry += "\n---\n"

        self._append("FEATURES.md", entry)
        logger.info("Logged feature request {}: {}", entry_id, capability[:100])
        return entry_id

    def _check_promotion(self, summary: str) -> None:
        """Check if a learning pattern has recurred enough to promote to rules.md."""
        # Simple keyword matching for recurrence detection
        learnings_file = self.learnings_dir / "LEARNINGS.md"
        if not learnings_file.is_file():
            return

        content = learnings_file.read_text(encoding="utf-8")
        # Count how many entries have similar summaries (simple word overlap)
        keywords = set(re.findall(r"\w{4,}", summary.lower()))
        if not keywords:
            return

        # Count entries with significant keyword overlap
        entries = content.split("## [LRN-")
        similar_count = 0
        for entry in entries[1:]:  # Skip header
            entry_words = set(re.findall(r"\w{4,}", entry.lower()))
            overlap = keywords & entry_words
            if len(overlap) >= max(2, len(keywords) // 2):
                similar_count += 1

        if similar_count >= _PROMOTION_THRESHOLD:
            self._promote_to_rules(summary)

    def _promote_to_rules(self, summary: str) -> None:
        """Promote a recurring learning to rules.md."""
        self.rules_file.parent.mkdir(parents=True, exist_ok=True)

        rule_line = f"\n- **Auto-learned**: {summary}\n"

        if self.rules_file.is_file():
            existing = self.rules_file.read_text(encoding="utf-8")
            # Don't duplicate
            if summary in existing:
                return
            self.rules_file.write_text(
                existing.rstrip() + "\n" + rule_line,
                encoding="utf-8",
            )
        else:
            self.rules_file.write_text(
                "# Rules\n\nStanding orders for Aradhya.\n\n"
                "## Auto-Promoted Learnings\n" + rule_line,
                encoding="utf-8",
            )

        logger.info("Promoted learning to rules.md: {}", summary[:80])

    def search(self, keyword: str) -> str:
        """Search all learning files for a keyword."""
        results: list[str] = []
        for filename in ("ERRORS.md", "LEARNINGS.md", "FEATURES.md"):
            path = self.learnings_dir / filename
            if not path.is_file():
                continue
            content = path.read_text(encoding="utf-8")
            if keyword.lower() in content.lower():
                # Extract matching entries
                for entry in content.split("## ["):
                    if keyword.lower() in entry.lower():
                        results.append(f"[{filename}] [{entry[:200]}...")

        if not results:
            return f"No learnings found matching '{keyword}'."
        return "\n\n".join(results[:10])

    def pending_count(self) -> dict[str, int]:
        """Count pending entries in each file."""
        counts = {}
        for filename in ("ERRORS.md", "LEARNINGS.md", "FEATURES.md"):
            path = self.learnings_dir / filename
            if path.is_file():
                content = path.read_text(encoding="utf-8")
                counts[filename] = content.count("**Status**: pending")
            else:
                counts[filename] = 0
        return counts

    def _append(self, filename: str, content: str) -> None:
        path = self.learnings_dir / filename
        with path.open("a", encoding="utf-8") as f:
            f.write(content)

    def _generate_id(self, prefix: str) -> str:
        stamp = datetime.now().strftime("%Y%m%d")
        # Use time-based suffix for uniqueness
        suffix = datetime.now().strftime("%H%M%S")
        return f"{prefix}-{stamp}-{suffix}"


# ── Tool definitions for the agent loop ──────────────────────────

@tool_definition(
    name="log_error",
    description=(
        "Log an error that occurred during tool execution or command failure. "
        "Use this when a tool call fails or produces unexpected results."
    ),
    parameters={
        "type": "object",
        "properties": {
            "tool_name": {
                "type": "string",
                "description": "Name of the tool or command that failed.",
            },
            "error_message": {
                "type": "string",
                "description": "The error message or failure description.",
            },
            "context": {
                "type": "string",
                "description": "Additional context about what was being attempted.",
            },
        },
        "required": ["tool_name", "error_message"],
    },
)
def log_error(tool_name: str, error_message: str, context: str = "") -> str:
    """Log an error to .learnings/ERRORS.md."""
    engine = LearningsEngine(Path(__file__).resolve().parents[3])
    entry_id = engine.log_error(tool_name, error_message, context)
    return f"Error logged as {entry_id}."


@tool_definition(
    name="log_learning",
    description=(
        "Log a learning, correction, or insight discovered during execution. "
        "Use this when the user corrects Aradhya, or when a better approach "
        "is discovered. Learnings that recur 3+ times are automatically "
        "promoted to permanent rules."
    ),
    parameters={
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "One of: correction, insight, knowledge_gap, best_practice",
            },
            "summary": {
                "type": "string",
                "description": "One-line description of what was learned.",
            },
            "details": {
                "type": "string",
                "description": "Full context about the learning.",
            },
        },
        "required": ["category", "summary"],
    },
)
def log_learning(category: str, summary: str, details: str = "") -> str:
    """Log a learning to .learnings/LEARNINGS.md."""
    engine = LearningsEngine(Path(__file__).resolve().parents[3])
    entry_id = engine.log_learning(category, summary, details)
    return f"Learning logged as {entry_id}."


@tool_definition(
    name="log_feature_request",
    description=(
        "Log a capability that the user requested but isn't available yet. "
        "This helps track what features to build next."
    ),
    parameters={
        "type": "object",
        "properties": {
            "capability": {
                "type": "string",
                "description": "What the user wanted to do.",
            },
            "user_context": {
                "type": "string",
                "description": "Why they needed it.",
            },
        },
        "required": ["capability"],
    },
)
def log_feature_request(capability: str, user_context: str = "") -> str:
    """Log a feature request to .learnings/FEATURES.md."""
    engine = LearningsEngine(Path(__file__).resolve().parents[3])
    entry_id = engine.log_feature_request(capability, user_context)
    return f"Feature request logged as {entry_id}."


@tool_definition(
    name="search_learnings",
    description="Search all learnings, errors, and feature requests for a keyword.",
    parameters={
        "type": "object",
        "properties": {
            "keyword": {
                "type": "string",
                "description": "The keyword to search for.",
            },
        },
        "required": ["keyword"],
    },
)
def search_learnings(keyword: str) -> str:
    """Search learning files."""
    engine = LearningsEngine(Path(__file__).resolve().parents[3])
    return engine.search(keyword)


ALL_LEARNINGS_TOOLS = [log_error, log_learning, log_feature_request, search_learnings]
