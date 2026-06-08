"""Subagent runner — ThreadPoolExecutor-based subagent spawner.

The runner is the execution engine for the subagent orchestration system.
It combines:

    * ``agent_defs.AgentDefinition`` — the persona and configuration
    * ``subagent_registry.SubagentRegistry`` — lifecycle tracking
    * ``subagent_messenger.SubagentMessenger`` — inter-agent comms

…and wraps them in a ``ThreadPoolExecutor`` so multiple subagents can
run concurrently.  Each subagent gets its own ``AgentLoop`` instance
with a scoped ``Session``.

Usage::

    runner = SubagentRunner.instance()
    sid = runner.spawn(
        role="researcher",
        prompt="Find all TODO comments in the codebase",
        parent_id="main",
    )
    result = runner.get_result(sid, timeout=120.0)
    print(result.output)
"""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Protocol

from loguru import logger

from src.aradhya.agents.subagent_messenger import SubagentMessenger
from src.aradhya.agents.subagent_registry import (
    SubagentInfo,
    SubagentRegistry,
    SubagentStatus,
)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SubagentResult:
    """Immutable result returned when a subagent completes.

    Attributes
    ----------
    subagent_id : str
        ID of the subagent.
    role : str
        The role the subagent was spawned with.
    status : SubagentStatus
        Final status (COMPLETED, FAILED, CANCELLED).
    output : str
        The primary text output (usually the model's final response).
    error : str
        Error message if the subagent failed.
    elapsed_seconds : float
        Wall-clock time the subagent ran for.
    metadata : dict[str, Any]
        Arbitrary metadata from the subagent's execution.
    """

    subagent_id: str
    role: str
    status: SubagentStatus
    output: str = ""
    error: str = ""
    elapsed_seconds: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Agent loop factory protocol
# ---------------------------------------------------------------------------

class AgentLoopFactory(Protocol):
    """Protocol for creating an agent loop for a subagent.

    Accepting a factory instead of importing AgentLoop directly avoids
    circular imports (agent_loop.py may import from the agents package).
    """

    def __call__(
        self,
        *,
        subagent_id: str,
        role: str,
        prompt: str,
        tools: list[str] | None = None,
        model: str = "",
        max_turns: int = 10,
        system_prompt: str = "",
    ) -> str:
        """Run a subagent loop and return the output text.

        The factory is responsible for:
        1. Creating a scoped Session for the subagent.
        2. Building a ToolRegistry (possibly filtered by *tools*).
        3. Running the ReAct loop to completion.
        4. Returning the final assistant response text.

        Raises on failure so the runner can capture the error.
        """
        ...


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

class SubagentRunner:
    """Singleton that manages concurrent subagent execution.

    Uses a ``ThreadPoolExecutor`` to run multiple subagents in parallel,
    each in its own thread.  Integrates with the ``SubagentRegistry``
    for lifecycle tracking and ``SubagentMessenger`` for inter-agent
    communication.

    Parameters
    ----------
    max_workers : int
        Maximum concurrent subagents (default 4).
    loop_factory : AgentLoopFactory | None
        Callable that creates and runs an agent loop.  Must be injected
        before spawning subagents — typically by ``AssistantCore`` during
        initialisation.
    """

    _instance: SubagentRunner | None = None
    _init_lock: threading.Lock = threading.Lock()

    MAX_WORKERS_DEFAULT: int = 4

    def __init__(self, max_workers: int = MAX_WORKERS_DEFAULT) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="aradhya-subagent",
        )
        self._registry = SubagentRegistry.instance()
        self._messenger = SubagentMessenger.instance()
        self._futures: dict[str, Future[SubagentResult]] = {}
        self._results: dict[str, SubagentResult] = {}  # cached completed results
        self._lock = threading.Lock()
        self._loop_factory: AgentLoopFactory | None = None

    @classmethod
    def instance(cls, max_workers: int = MAX_WORKERS_DEFAULT) -> SubagentRunner:
        """Return the process-wide singleton."""
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = cls(max_workers=max_workers)
                    logger.debug("SubagentRunner singleton created")
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Tear down the singleton (for tests)."""
        with cls._init_lock:
            if cls._instance is not None:
                cls._instance.shutdown()
            cls._instance = None

    def set_loop_factory(self, factory: AgentLoopFactory) -> None:
        """Inject the agent loop factory.

        Must be called before ``spawn()``.  Typically done once by
        ``AssistantCore`` during startup.
        """
        self._loop_factory = factory
        logger.debug("Agent loop factory set on SubagentRunner")

    # ── Spawn ─────────────────────────────────────────────────────────

    def spawn(
        self,
        role: str,
        prompt: str,
        *,
        parent_id: str | None = None,
        tools: list[str] | None = None,
        model: str = "",
        max_turns: int = 10,
        system_prompt: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Spawn a subagent in a background thread.

        Returns the subagent_id (UUID4 string).  The subagent starts
        running immediately in the thread pool.

        Raises
        ------
        RuntimeError
            If no loop factory has been set.
        """
        if self._loop_factory is None:
            raise RuntimeError(
                "No agent loop factory has been set on SubagentRunner. "
                "Call set_loop_factory() first."
            )

        subagent_id = str(uuid.uuid4())

        # Register in the global registry
        info = SubagentInfo(
            subagent_id=subagent_id,
            role=role,
            status=SubagentStatus.PENDING,
            parent_id=parent_id,
            tools=tools or [],
            metadata=metadata or {},
        )
        self._registry.register(info)
        self._messenger.register_agent(subagent_id)

        # Submit to the thread pool
        future = self._executor.submit(
            self._run_subagent,
            subagent_id=subagent_id,
            role=role,
            prompt=prompt,
            tools=tools,
            model=model,
            max_turns=max_turns,
            system_prompt=system_prompt,
            parent_id=parent_id,
        )

        with self._lock:
            self._futures[subagent_id] = future

        logger.info(
            "Spawned subagent '{}' (role={}, parent={})",
            subagent_id[:8],
            role,
            (parent_id or "<root>")[:8],
        )
        return subagent_id

    # ── Execution (runs in thread pool) ───────────────────────────────

    def _run_subagent(
        self,
        *,
        subagent_id: str,
        role: str,
        prompt: str,
        tools: list[str] | None,
        model: str,
        max_turns: int,
        system_prompt: str,
        parent_id: str | None,
    ) -> SubagentResult:
        """Execute a subagent's ReAct loop in a background thread.

        This method runs inside the ThreadPoolExecutor.
        """
        assert self._loop_factory is not None

        self._registry.update_status(subagent_id, SubagentStatus.RUNNING)
        start_time = datetime.now()

        try:
            output = self._loop_factory(
                subagent_id=subagent_id,
                role=role,
                prompt=prompt,
                tools=tools,
                model=model,
                max_turns=max_turns,
                system_prompt=system_prompt,
            )

            self._registry.update_status(
                subagent_id, SubagentStatus.COMPLETED
            )

            result = SubagentResult(
                subagent_id=subagent_id,
                role=role,
                status=SubagentStatus.COMPLETED,
                output=output,
                elapsed_seconds=(datetime.now() - start_time).total_seconds(),
            )

            # Notify parent via messenger
            if parent_id:
                self._messenger.send(
                    subagent_id,
                    parent_id,
                    f"[Subagent {role} completed]\n{output[:2000]}",
                    metadata={"status": "completed"},
                )

            logger.info(
                "Subagent '{}' (role={}) completed in {:.1f}s",
                subagent_id[:8],
                role,
                result.elapsed_seconds,
            )
            return result

        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            self._registry.update_status(
                subagent_id, SubagentStatus.FAILED, error=error_msg
            )

            result = SubagentResult(
                subagent_id=subagent_id,
                role=role,
                status=SubagentStatus.FAILED,
                error=error_msg,
                elapsed_seconds=(datetime.now() - start_time).total_seconds(),
            )

            # Notify parent of failure
            if parent_id:
                self._messenger.send(
                    subagent_id,
                    parent_id,
                    f"[Subagent {role} failed: {error_msg}]",
                    metadata={"status": "failed", "error": error_msg},
                )

            logger.error(
                "Subagent '{}' (role={}) failed: {}",
                subagent_id[:8],
                role,
                error_msg,
            )
            return result

        finally:
            self._messenger.unregister_agent(subagent_id)
            with self._lock:
                self._results[subagent_id] = result
                self._futures.pop(subagent_id, None)

    # ── Result retrieval ──────────────────────────────────────────────

    def get_result(
        self, subagent_id: str, timeout: float = 120.0
    ) -> SubagentResult | None:
        """Block until the subagent completes (or *timeout* elapses).

        Returns ``None`` if the subagent_id is not found or timed out.
        """
        with self._lock:
            future = self._futures.get(subagent_id)

        if future is None:
            # Already completed — check cached results first
            with self._lock:
                cached = self._results.get(subagent_id)
            if cached is not None:
                return cached

            # Fallback: check registry for final state
            info = self._registry.get(subagent_id)
            if info is not None and info.status in (
                SubagentStatus.COMPLETED,
                SubagentStatus.FAILED,
                SubagentStatus.CANCELLED,
            ):
                return SubagentResult(
                    subagent_id=subagent_id,
                    role=info.role,
                    status=info.status,
                    error=info.error,
                )
            return None

        try:
            return future.result(timeout=timeout)
        except TimeoutError:
            logger.warning(
                "Timeout waiting for subagent '{}' after {:.0f}s",
                subagent_id[:8],
                timeout,
            )
            return None
        except Exception as exc:
            return SubagentResult(
                subagent_id=subagent_id,
                role="unknown",
                status=SubagentStatus.FAILED,
                error=str(exc),
            )

    # ── Management ────────────────────────────────────────────────────

    def list_active(self) -> list[SubagentInfo]:
        """Return all currently running or pending subagents."""
        return self._registry.list_active()

    def kill(self, subagent_id: str) -> bool:
        """Cancel a running subagent.

        Returns ``True`` if the subagent was found and cancellation was
        attempted.  Note that cancellation is best-effort — the thread
        may not terminate immediately.
        """
        with self._lock:
            future = self._futures.get(subagent_id)

        if future is None:
            return False

        cancelled = future.cancel()
        if not cancelled:
            # Already running — mark as cancelled in registry
            self._registry.update_status(
                subagent_id, SubagentStatus.CANCELLED
            )
        else:
            self._registry.update_status(
                subagent_id, SubagentStatus.CANCELLED
            )
            with self._lock:
                self._futures.pop(subagent_id, None)

        logger.info("Kill requested for subagent '{}'", subagent_id[:8])
        return True

    def kill_all(self) -> int:
        """Cancel all running subagents.  Returns the count killed."""
        with self._lock:
            ids = list(self._futures.keys())
        count = 0
        for sid in ids:
            if self.kill(sid):
                count += 1
        return count

    # ── Shutdown ──────────────────────────────────────────────────────

    def shutdown(self, wait: bool = False) -> None:
        """Shut down the thread pool.

        Parameters
        ----------
        wait : bool
            If True, block until all running subagents finish.
        """
        self.kill_all()
        self._executor.shutdown(wait=wait)
        self._registry.clear()
        self._messenger.clear()
        logger.info("SubagentRunner shut down")
