"""Simple task scheduler for background automation.

Inspired by OpenClaw's cron jobs system, this module provides a lightweight
scheduler that can run tasks at specified intervals.  Tasks are defined in
a JSON configuration file and executed in a background thread.
"""

from __future__ import annotations

import json
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from loguru import logger

DEFAULT_SCHEDULES_FILE = Path.home() / ".aradhya" / "schedules.json"


@dataclass
class ScheduledTask:
    """A task that runs on a schedule."""
    id: str
    description: str
    action: str  # "shell", "message", "refresh"
    payload: str
    interval_minutes: int = 60
    enabled: bool = True
    last_run: str = ""

    def is_due(self) -> bool:
        """Check if this task is due to run."""
        if not self.enabled:
            return False
        if not self.last_run:
            return True
        try:
            last = datetime.fromisoformat(self.last_run)
            elapsed = (datetime.now() - last).total_seconds() / 60
            return elapsed >= self.interval_minutes
        except (ValueError, TypeError):
            return True


class TaskScheduler:
    """Background scheduler that runs tasks at configured intervals.

    The scheduler runs in a daemon thread and checks for due tasks
    every 60 seconds.

    Parameters
    ----------
    schedules_file
        Path to the JSON file that persists task definitions.
    on_message
        Callback for ``"message"`` actions.
    on_agent_think
        Callback for ``"agent_think"`` actions.  Receives the task
        payload and should route it through the full planning pipeline.
        This is the heartbeat mechanism — equivalent to OpenClaw's cron
        heartbeat that spawns an isolated agent session.
    """

    def __init__(
        self,
        schedules_file: Path | None = None,
        on_message: Callable[[str], None] | None = None,
        on_agent_think: Callable[[str], None] | None = None,
    ) -> None:
        self.schedules_file = schedules_file or DEFAULT_SCHEDULES_FILE
        self.on_message = on_message
        self.on_agent_think = on_agent_think
        self._tasks: dict[str, ScheduledTask] = {}
        self._running = False
        self._thread: threading.Thread | None = None
        self._load_tasks()

    def _load_tasks(self) -> None:
        """Load tasks from the schedules file."""
        if not self.schedules_file.is_file():
            return

        try:
            raw = self.schedules_file.read_text(encoding="utf-8")
            data = json.loads(raw)
            for task_data in data.get("tasks", []):
                task = ScheduledTask(
                    id=task_data["id"],
                    description=task_data.get("description", ""),
                    action=task_data.get("action", "shell"),
                    payload=task_data.get("payload", ""),
                    interval_minutes=task_data.get("interval_minutes", 60),
                    enabled=task_data.get("enabled", True),
                    last_run=task_data.get("last_run", ""),
                )
                self._tasks[task.id] = task
            logger.info(
                "Loaded {} scheduled task(s) from {}",
                len(self._tasks),
                self.schedules_file,
            )
        except (json.JSONDecodeError, KeyError) as error:
            logger.warning("Failed to load schedules: {}", error)

    def _save_tasks(self) -> None:
        """Persist tasks back to the schedules file."""
        self.schedules_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "tasks": [
                {
                    "id": t.id,
                    "description": t.description,
                    "action": t.action,
                    "payload": t.payload,
                    "interval_minutes": t.interval_minutes,
                    "enabled": t.enabled,
                    "last_run": t.last_run,
                }
                for t in self._tasks.values()
            ]
        }
        self.schedules_file.write_text(
            json.dumps(data, indent=2) + "\n",
            encoding="utf-8",
        )

    def add_task(
        self,
        task_id: str,
        description: str,
        action: str,
        payload: str,
        interval_minutes: int = 60,
    ) -> ScheduledTask:
        """Add or update a scheduled task."""
        task = ScheduledTask(
            id=task_id,
            description=description,
            action=action,
            payload=payload,
            interval_minutes=interval_minutes,
        )
        self._tasks[task_id] = task
        self._save_tasks()
        logger.info("Added scheduled task: {} (every {} min)", task_id, interval_minutes)
        return task

    def remove_task(self, task_id: str) -> bool:
        """Remove a scheduled task."""
        if task_id in self._tasks:
            del self._tasks[task_id]
            self._save_tasks()
            return True
        return False

    def list_tasks(self) -> list[ScheduledTask]:
        """Return all configured tasks."""
        return list(self._tasks.values())

    def start(self) -> None:
        """Start the background scheduler thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="aradhya-scheduler"
        )
        self._thread.start()
        logger.info("Task scheduler started")

    def stop(self) -> None:
        """Stop the background scheduler."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("Task scheduler stopped")

    def _run_loop(self) -> None:
        """Main scheduler loop — checks for due tasks every 60 seconds."""
        while self._running:
            for task in self._tasks.values():
                if task.is_due():
                    self._execute_task(task)
            time.sleep(60)

    def _execute_task(self, task: ScheduledTask) -> None:
        """Execute a single scheduled task."""
        logger.info("Executing scheduled task: {} ({})", task.id, task.action)
        try:
            if task.action == "shell":
                result = subprocess.run(
                    task.payload,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                logger.info(
                    "Task '{}' completed (exit={}): {}",
                    task.id,
                    result.returncode,
                    result.stdout[:200],
                )

            elif task.action == "message" and self.on_message:
                self.on_message(task.payload)

            elif task.action == "agent_think" and self.on_agent_think:
                # Heartbeat mechanism: route the payload through the full
                # AgentLoop so the assistant can think, call tools, and act
                # autonomously.  This mirrors OpenClaw's cron heartbeat
                # that spawns an isolated agent session.
                self.on_agent_think(task.payload)

            elif task.action == "refresh":
                logger.info("Task '{}': refresh signal sent", task.id)

            task.last_run = datetime.now().isoformat(timespec="seconds")
            self._save_tasks()

        except subprocess.TimeoutExpired:
            logger.warning("Task '{}' timed out", task.id)
        except Exception as error:
            logger.error("Task '{}' failed: {}", task.id, error)
