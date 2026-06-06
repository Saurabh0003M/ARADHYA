"""Subagent registry — thread-safe tracking of active subagents.

Maintains a global registry of all spawned subagents, their statuses,
and parent-child relationships.  Every subsystem that needs to discover
or enumerate running subagents goes through this singleton.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any

from loguru import logger


class SubagentStatus(Enum):
    """Lifecycle status of a subagent."""

    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()


@dataclass
class SubagentInfo:
    """Metadata for a single registered subagent."""

    subagent_id: str
    role: str
    status: SubagentStatus = SubagentStatus.PENDING
    parent_id: str | None = None
    session_id: str | None = None
    created_at: str = ""
    completed_at: str = ""
    tools: list[str] = field(default_factory=list)
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now().isoformat(timespec="seconds")


class SubagentRegistry:
    """Singleton registry that tracks every active subagent.

    Thread-safe — all mutations are guarded by an internal lock.

    Usage::

        registry = SubagentRegistry.instance()
        registry.register(info)
        registry.update_status(subagent_id, SubagentStatus.RUNNING)
        active = registry.list_active()
    """

    _instance: SubagentRegistry | None = None
    _init_lock: threading.Lock = threading.Lock()

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._agents: dict[str, SubagentInfo] = {}
        # parent_id -> set of child subagent_ids
        self._children: dict[str, set[str]] = {}

    @classmethod
    def instance(cls) -> SubagentRegistry:
        """Return the process-wide singleton, creating it on first call."""
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = cls()
                    logger.debug("SubagentRegistry singleton created")
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Tear down the singleton (for tests)."""
        with cls._init_lock:
            cls._instance = None

    # ── Registration ──────────────────────────────────────────────────

    def register(self, info: SubagentInfo) -> None:
        """Register a new subagent in the registry."""
        with self._lock:
            self._agents[info.subagent_id] = info
            if info.parent_id:
                self._children.setdefault(info.parent_id, set()).add(
                    info.subagent_id
                )
        logger.debug(
            "Registered subagent '{}' (role={}, parent={})",
            info.subagent_id,
            info.role,
            info.parent_id or "<root>",
        )

    def unregister(self, subagent_id: str) -> SubagentInfo | None:
        """Remove a subagent from the registry.

        Returns the removed ``SubagentInfo`` or ``None`` if not found.
        """
        with self._lock:
            info = self._agents.pop(subagent_id, None)
            if info is None:
                return None
            # Clean up parent-child mappings
            if info.parent_id and info.parent_id in self._children:
                self._children[info.parent_id].discard(subagent_id)
                if not self._children[info.parent_id]:
                    del self._children[info.parent_id]
            # Remove any child entries for this agent
            self._children.pop(subagent_id, None)
        logger.debug("Unregistered subagent '{}'", subagent_id)
        return info

    # ── Status updates ────────────────────────────────────────────────

    def update_status(
        self,
        subagent_id: str,
        status: SubagentStatus,
        *,
        error: str = "",
    ) -> None:
        """Update the status of a registered subagent."""
        with self._lock:
            info = self._agents.get(subagent_id)
            if info is None:
                logger.warning(
                    "Cannot update status — subagent '{}' not found",
                    subagent_id,
                )
                return
            info.status = status
            if error:
                info.error = error
            if status in (
                SubagentStatus.COMPLETED,
                SubagentStatus.FAILED,
                SubagentStatus.CANCELLED,
            ):
                info.completed_at = datetime.now().isoformat(
                    timespec="seconds"
                )

    # ── Queries ───────────────────────────────────────────────────────

    def get(self, subagent_id: str) -> SubagentInfo | None:
        """Return the ``SubagentInfo`` for *subagent_id*, or ``None``."""
        with self._lock:
            return self._agents.get(subagent_id)

    def list_all(self) -> list[SubagentInfo]:
        """Return a snapshot of every registered subagent."""
        with self._lock:
            return list(self._agents.values())

    def list_active(self) -> list[SubagentInfo]:
        """Return only subagents that are PENDING or RUNNING."""
        with self._lock:
            return [
                info
                for info in self._agents.values()
                if info.status
                in (SubagentStatus.PENDING, SubagentStatus.RUNNING)
            ]

    def get_children(self, parent_id: str) -> list[SubagentInfo]:
        """Return all direct child subagents of *parent_id*."""
        with self._lock:
            child_ids = self._children.get(parent_id, set())
            return [
                self._agents[cid]
                for cid in child_ids
                if cid in self._agents
            ]

    def get_parent(self, subagent_id: str) -> SubagentInfo | None:
        """Return the parent of *subagent_id*, or ``None`` if root."""
        with self._lock:
            info = self._agents.get(subagent_id)
            if info is None or info.parent_id is None:
                return None
            return self._agents.get(info.parent_id)

    @property
    def count(self) -> int:
        """Total number of registered subagents (any status)."""
        with self._lock:
            return len(self._agents)

    @property
    def active_count(self) -> int:
        """Number of PENDING or RUNNING subagents."""
        with self._lock:
            return sum(
                1
                for info in self._agents.values()
                if info.status
                in (SubagentStatus.PENDING, SubagentStatus.RUNNING)
            )

    # ── Cleanup ───────────────────────────────────────────────────────

    def clear(self) -> None:
        """Remove all entries (useful during shutdown)."""
        with self._lock:
            self._agents.clear()
            self._children.clear()
        logger.debug("SubagentRegistry cleared")
