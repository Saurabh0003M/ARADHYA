"""Async telemetry and score calculation for the smart model router.

Latency is intentionally scoped to provider call time only: record the duration
from the outbound API send to the first token for streams, or to full response
receipt for non-streaming calls. Do not include local request classification,
queueing, planning, or hidden provider-side thinking metadata.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
from typing import Iterable

from pydantic import BaseModel, Field, field_validator

try:  # pragma: no cover - exercised only when the optional dependency exists.
    import aiosqlite  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - the stdlib fallback is covered in tests.
    aiosqlite = None  # type: ignore[assignment]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def hour_slot(value: datetime | None = None) -> str:
    stamp = value or utc_now()
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    stamp = stamp.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    return stamp.strftime("%Y-%m-%dT%H:00")


class ModelCallTelemetry(BaseModel):
    """One provider attempt in a routed request."""

    request_id: str
    timestamp: datetime = Field(default_factory=utc_now)
    model_id: str
    provider: str
    capability_group: str
    task_type: str
    latency_ms: int = Field(ge=0)
    success: bool
    error_code: str | None = None
    tokens_in: int = Field(default=0, ge=0)
    tokens_out: int = Field(default=0, ge=0)

    @field_validator("request_id", "model_id", "provider", "capability_group", "task_type")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must be non-empty")
        return stripped

    @property
    def timestamp_slot(self) -> str:
        return hour_slot(self.timestamp)


class ModelScore(BaseModel):
    """Live score for one model inside one capability group."""

    model_id: str
    capability_group: str
    score: float
    success_rate_24h: float
    latency_score: float
    availability_now: float
    sample_size_24h: int
    calculated_at: datetime = Field(default_factory=utc_now)


@dataclass(frozen=True)
class ModelMetricSnapshot:
    """Telemetry aggregate used by routing strategies."""

    model_id: str
    attempts_24h: int = 0
    successes_24h: int = 0
    success_rate_24h: float = 1.0
    avg_latency_ms_24h: float | None = None
    avg_latency_ms_current_hour: float | None = None


class SQLiteTelemetryStore:
    """Async SQLite telemetry store.

    If ``aiosqlite`` is installed, operations use it directly. Otherwise the
    implementation falls back to ``sqlite3`` inside ``asyncio.to_thread`` so the
    router can run in a minimal local install.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    async def init(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        schema = """
        CREATE TABLE IF NOT EXISTS model_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            model_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            capability_group TEXT NOT NULL,
            task_type TEXT NOT NULL,
            latency_ms INTEGER NOT NULL,
            success INTEGER NOT NULL,
            error_code TEXT,
            tokens_in INTEGER NOT NULL DEFAULT 0,
            tokens_out INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_model_calls_request_id ON model_calls(request_id);
        CREATE INDEX IF NOT EXISTS idx_model_calls_model_group_time
            ON model_calls(model_id, capability_group, timestamp);
        CREATE INDEX IF NOT EXISTS idx_model_calls_provider ON model_calls(provider);

        CREATE TABLE IF NOT EXISTS model_scores (
            model_id TEXT NOT NULL,
            capability_group TEXT NOT NULL,
            score REAL NOT NULL,
            success_rate_24h REAL NOT NULL,
            latency_score REAL NOT NULL,
            availability_now REAL NOT NULL,
            sample_size_24h INTEGER NOT NULL,
            calculated_at TEXT NOT NULL,
            PRIMARY KEY (model_id, capability_group)
        );
        """
        if aiosqlite is not None:
            async with aiosqlite.connect(self.db_path) as db:  # type: ignore[union-attr]
                await db.executescript(schema)
                await db.commit()
            return

        await asyncio.to_thread(self._executescript_sync, schema)

    async def record_call(self, telemetry: ModelCallTelemetry) -> None:
        payload = (
            telemetry.request_id,
            telemetry.timestamp_slot,
            telemetry.model_id,
            telemetry.provider,
            telemetry.capability_group,
            telemetry.task_type,
            telemetry.latency_ms,
            1 if telemetry.success else 0,
            telemetry.error_code,
            telemetry.tokens_in,
            telemetry.tokens_out,
        )
        statement = """
        INSERT INTO model_calls (
            request_id, timestamp, model_id, provider, capability_group, task_type,
            latency_ms, success, error_code, tokens_in, tokens_out
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        if aiosqlite is not None:
            async with aiosqlite.connect(self.db_path) as db:  # type: ignore[union-attr]
                await db.execute(statement, payload)
                await db.commit()
            return

        await asyncio.to_thread(self._execute_sync, statement, payload)

    async def metric_snapshots(
        self,
        model_ids: Iterable[str],
        capability_group: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, ModelMetricSnapshot]:
        ids = tuple(dict.fromkeys(model_ids))
        if not ids:
            return {}

        current_slot = hour_slot(now)
        since_slot = hour_slot((now or utc_now()) - timedelta(hours=23))
        placeholders = ",".join("?" for _ in ids)
        params = (capability_group, since_slot, *ids)
        statement = f"""
        SELECT
            model_id,
            COUNT(*) AS attempts_24h,
            SUM(success) AS successes_24h,
            AVG(CASE WHEN success = 1 THEN latency_ms END) AS avg_latency_ms_24h,
            AVG(CASE WHEN timestamp = ? AND success = 1 THEN latency_ms END)
                AS avg_latency_ms_current_hour
        FROM model_calls
        WHERE capability_group = ?
          AND timestamp >= ?
          AND model_id IN ({placeholders})
        GROUP BY model_id
        """
        query_params = (current_slot, *params)

        if aiosqlite is not None:
            async with aiosqlite.connect(self.db_path) as db:  # type: ignore[union-attr]
                db.row_factory = sqlite3.Row
                cursor = await db.execute(statement, query_params)
                rows = await cursor.fetchall()
        else:
            rows = await asyncio.to_thread(self._fetchall_sync, statement, query_params)

        snapshots = {
            model_id: ModelMetricSnapshot(model_id=model_id)
            for model_id in ids
        }
        for row in rows:
            attempts = int(row["attempts_24h"] or 0)
            successes = int(row["successes_24h"] or 0)
            snapshots[row["model_id"]] = ModelMetricSnapshot(
                model_id=row["model_id"],
                attempts_24h=attempts,
                successes_24h=successes,
                success_rate_24h=(successes / attempts) if attempts else 1.0,
                avg_latency_ms_24h=(
                    float(row["avg_latency_ms_24h"])
                    if row["avg_latency_ms_24h"] is not None
                    else None
                ),
                avg_latency_ms_current_hour=(
                    float(row["avg_latency_ms_current_hour"])
                    if row["avg_latency_ms_current_hour"] is not None
                    else None
                ),
            )
        return snapshots

    async def recalculate_scores(
        self,
        model_ids: Iterable[str],
        capability_group: str,
        *,
        availability_now: dict[str, float] | None = None,
        latency_baseline_ms: int = 4000,
        now: datetime | None = None,
    ) -> dict[str, ModelScore]:
        snapshots = await self.metric_snapshots(model_ids, capability_group, now=now)
        availability_now = availability_now or {}
        scores: dict[str, ModelScore] = {}
        for model_id, snapshot in snapshots.items():
            latency_ms = snapshot.avg_latency_ms_current_hour or snapshot.avg_latency_ms_24h
            latency_score = self._latency_score(latency_ms, latency_baseline_ms)
            availability = max(0.0, min(1.0, availability_now.get(model_id, 1.0)))
            score = (
                (snapshot.success_rate_24h * 0.5)
                + (latency_score * 0.3)
                + (availability * 0.2)
            )
            scores[model_id] = ModelScore(
                model_id=model_id,
                capability_group=capability_group,
                score=score,
                success_rate_24h=snapshot.success_rate_24h,
                latency_score=latency_score,
                availability_now=availability,
                sample_size_24h=snapshot.attempts_24h,
                calculated_at=now or utc_now(),
            )

        await self._persist_scores(scores.values())
        return scores

    @staticmethod
    def _latency_score(latency_ms: float | None, latency_baseline_ms: int) -> float:
        if latency_ms is None:
            return 0.75
        baseline = max(latency_baseline_ms, 1)
        return 1.0 / (1.0 + (max(latency_ms, 1.0) / baseline))

    async def _persist_scores(self, scores: Iterable[ModelScore]) -> None:
        rows = [
            (
                score.model_id,
                score.capability_group,
                score.score,
                score.success_rate_24h,
                score.latency_score,
                score.availability_now,
                score.sample_size_24h,
                score.calculated_at.isoformat(),
            )
            for score in scores
        ]
        if not rows:
            return

        statement = """
        INSERT INTO model_scores (
            model_id, capability_group, score, success_rate_24h, latency_score,
            availability_now, sample_size_24h, calculated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(model_id, capability_group) DO UPDATE SET
            score = excluded.score,
            success_rate_24h = excluded.success_rate_24h,
            latency_score = excluded.latency_score,
            availability_now = excluded.availability_now,
            sample_size_24h = excluded.sample_size_24h,
            calculated_at = excluded.calculated_at
        """
        if aiosqlite is not None:
            async with aiosqlite.connect(self.db_path) as db:  # type: ignore[union-attr]
                await db.executemany(statement, rows)
                await db.commit()
            return

        await asyncio.to_thread(self._executemany_sync, statement, rows)

    def _connect_sync(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _executescript_sync(self, script: str) -> None:
        with self._connect_sync() as connection:
            connection.executescript(script)
            connection.commit()

    def _execute_sync(self, statement: str, params: tuple[object, ...]) -> None:
        with self._connect_sync() as connection:
            connection.execute(statement, params)
            connection.commit()

    def _executemany_sync(
        self,
        statement: str,
        params: list[tuple[object, ...]],
    ) -> None:
        with self._connect_sync() as connection:
            connection.executemany(statement, params)
            connection.commit()

    def _fetchall_sync(
        self,
        statement: str,
        params: tuple[object, ...],
    ) -> list[sqlite3.Row]:
        with self._connect_sync() as connection:
            return list(connection.execute(statement, params).fetchall())
