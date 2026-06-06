"""Subagent messenger — queue-based inter-agent communication.

Provides thread-safe, in-process message passing between agents using
one ``queue.Queue`` per agent.  Supports point-to-point ``send``,
``broadcast`` to all active agents, and blocking ``receive`` with
timeout.

Follows the singleton pattern so every subsystem shares one messenger.
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from loguru import logger


@dataclass(frozen=True)
class Message:
    """An immutable message exchanged between agents.

    Attributes
    ----------
    sender : str
        ID of the sending agent.
    recipient : str
        ID of the intended recipient (``"*"`` for broadcast).
    content : str
        The message payload.
    timestamp : str
        ISO-8601 timestamp of when the message was created.
    metadata : dict[str, Any]
        Optional key-value pairs for routing, priority, etc.
    """

    sender: str
    recipient: str
    content: str
    timestamp: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # frozen dataclass needs object.__setattr__ for defaults
        if not self.timestamp:
            object.__setattr__(
                self,
                "timestamp",
                datetime.now().isoformat(timespec="milliseconds"),
            )


class SubagentMessenger:
    """Singleton message bus for inter-agent communication.

    Each agent is assigned a ``queue.Queue`` on first ``send`` or
    ``receive``.  Queues are unbounded by default (agents are expected
    to drain them) but the messenger caps the per-agent backlog to
    prevent runaway memory.

    Usage::

        messenger = SubagentMessenger.instance()
        messenger.send("agent-A", "agent-B", "hello")
        msg = messenger.receive("agent-B", timeout=5.0)
    """

    _instance: SubagentMessenger | None = None
    _init_lock: threading.Lock = threading.Lock()

    # Maximum messages buffered per agent before old messages are dropped
    MAX_QUEUE_SIZE: int = 500

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._queues: dict[str, queue.Queue[Message]] = {}

    @classmethod
    def instance(cls) -> SubagentMessenger:
        """Return the process-wide singleton."""
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = cls()
                    logger.debug("SubagentMessenger singleton created")
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Tear down the singleton (for tests)."""
        with cls._init_lock:
            cls._instance = None

    # ── Queue management ──────────────────────────────────────────────

    def _get_queue(self, agent_id: str) -> queue.Queue[Message]:
        """Return (or lazily create) the queue for *agent_id*."""
        with self._lock:
            if agent_id not in self._queues:
                self._queues[agent_id] = queue.Queue(
                    maxsize=self.MAX_QUEUE_SIZE
                )
            return self._queues[agent_id]

    def register_agent(self, agent_id: str) -> None:
        """Pre-create a queue for *agent_id* (idempotent)."""
        self._get_queue(agent_id)

    def unregister_agent(self, agent_id: str) -> None:
        """Remove the queue for *agent_id*, discarding pending messages."""
        with self._lock:
            q = self._queues.pop(agent_id, None)
        if q is not None:
            # Drain the queue to unblock any waiting readers
            while not q.empty():
                try:
                    q.get_nowait()
                except queue.Empty:
                    break
            logger.debug(
                "Unregistered messenger queue for agent '{}'", agent_id
            )

    # ── Send / Receive ────────────────────────────────────────────────

    def send(
        self,
        from_id: str,
        to_id: str,
        content: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Send a message from *from_id* to *to_id*.

        If the recipient's queue is full, the oldest message is dropped
        to make room (ring-buffer semantics).
        """
        msg = Message(
            sender=from_id,
            recipient=to_id,
            content=content,
            metadata=metadata or {},
        )
        q = self._get_queue(to_id)
        try:
            q.put_nowait(msg)
        except queue.Full:
            # Drop oldest to make room
            try:
                q.get_nowait()
            except queue.Empty:
                pass
            try:
                q.put_nowait(msg)
            except queue.Full:
                logger.warning(
                    "Message from '{}' to '{}' dropped — queue full",
                    from_id,
                    to_id,
                )
                return
        logger.debug("Message sent: {} -> {} ({} chars)", from_id, to_id, len(content))

    def receive(
        self,
        agent_id: str,
        timeout: float = 5.0,
    ) -> Message | None:
        """Block until a message arrives for *agent_id*, or *timeout* elapses.

        Returns ``None`` on timeout.
        """
        q = self._get_queue(agent_id)
        try:
            return q.get(timeout=timeout)
        except queue.Empty:
            return None

    def receive_nowait(self, agent_id: str) -> Message | None:
        """Non-blocking receive — returns ``None`` immediately if empty."""
        q = self._get_queue(agent_id)
        try:
            return q.get_nowait()
        except queue.Empty:
            return None

    def broadcast(
        self,
        from_id: str,
        content: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Send *content* to every registered agent (except the sender).

        Returns the number of agents the message was delivered to.
        """
        with self._lock:
            target_ids = [
                aid for aid in self._queues if aid != from_id
            ]
        for target_id in target_ids:
            self.send(from_id, target_id, content, metadata=metadata)
        logger.debug(
            "Broadcast from '{}' to {} agent(s)", from_id, len(target_ids)
        )
        return len(target_ids)

    # ── Introspection ─────────────────────────────────────────────────

    def pending_count(self, agent_id: str) -> int:
        """Return the number of messages waiting for *agent_id*."""
        q = self._get_queue(agent_id)
        return q.qsize()

    def registered_agents(self) -> list[str]:
        """Return IDs of all agents with active queues."""
        with self._lock:
            return list(self._queues.keys())

    # ── Cleanup ───────────────────────────────────────────────────────

    def clear(self) -> None:
        """Drop all queues and pending messages (shutdown)."""
        with self._lock:
            self._queues.clear()
        logger.debug("SubagentMessenger cleared")
