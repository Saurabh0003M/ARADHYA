"""Per-turn performance metrics — record and summarise where time went.

One :class:`TurnMetrics` row is written per completed agent turn to
``~/.aradhya/metrics/turns.jsonl`` (append-only, event-sourced like the audit
log). Each row carries the wall-clock breakdown that explains a slow turn:

- ``total_seconds``  — user prompt → final response, measured with a monotonic
  clock in ``assistant_core``.
- ``model_seconds``  — cumulative time inside model-provider calls (prefill +
  generation + any reload). On CPU this is usually the bulk of a slow turn.
- ``tool_seconds``   — cumulative time executing tool calls.
- ``overhead_seconds`` (computed) — whatever is left: context assembly,
  planning, session I/O. A large overhead points at Aradhya's own pipeline,
  not the model.
- ``iterations`` / ``tool_calls`` — how many ReAct rounds the turn took; every
  extra round re-pays the prompt-prefill cost.
- ``prompt_tokens`` / ``gen_tokens`` / ``load_seconds`` — the Ollama counters
  (``prompt_eval_count`` / ``eval_count`` / ``load_duration``) summed across the
  turn's model calls. A big ``prompt_tokens`` is the tool-schema prefill tax; a
  big ``load_seconds`` is a model reload/eviction.

The pure helpers (:func:`format_summary`, serialisation) are kept separate from
the file I/O so they can be unit-tested without touching disk.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from src.aradhya.paths import metrics_dir

_METRICS_FILENAME = "turns.jsonl"
# Keep the on-disk log bounded; we only ever summarise the recent tail.
_MAX_ROWS = 2000


@dataclass(frozen=True)
class TurnMetrics:
    """Wall-clock and token breakdown for a single agent turn."""

    turn_id: str
    model: str
    provider: str
    total_seconds: float
    model_seconds: float
    tool_seconds: float
    iterations: int
    tool_calls: int
    prompt_tokens: int = 0
    gen_tokens: int = 0
    load_seconds: float = 0.0
    success: bool = True
    timestamp: float = field(default_factory=time.time)

    @property
    def overhead_seconds(self) -> float:
        """Wall-clock not spent in model or tool calls (never negative)."""
        return max(0.0, self.total_seconds - self.model_seconds - self.tool_seconds)

    def to_record(self) -> dict[str, Any]:
        """Serialise to a JSON-safe dict, floats rounded, computed fields added."""
        record = asdict(self)
        for key in (
            "total_seconds",
            "model_seconds",
            "tool_seconds",
            "load_seconds",
            "timestamp",
        ):
            record[key] = round(float(record[key]), 3)
        record["overhead_seconds"] = round(self.overhead_seconds, 3)
        return record

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "TurnMetrics":
        """Rebuild from a stored row, ignoring computed/unknown extra keys."""
        fields = {
            "turn_id": str(record.get("turn_id", "")),
            "model": str(record.get("model", "")),
            "provider": str(record.get("provider", "")),
            "total_seconds": float(record.get("total_seconds", 0.0)),
            "model_seconds": float(record.get("model_seconds", 0.0)),
            "tool_seconds": float(record.get("tool_seconds", 0.0)),
            "iterations": int(record.get("iterations", 0)),
            "tool_calls": int(record.get("tool_calls", 0)),
            "prompt_tokens": int(record.get("prompt_tokens", 0)),
            "gen_tokens": int(record.get("gen_tokens", 0)),
            "load_seconds": float(record.get("load_seconds", 0.0)),
            "success": bool(record.get("success", True)),
            "timestamp": float(record.get("timestamp", 0.0)),
        }
        return cls(**fields)


def _metrics_path(path: Path | None = None) -> Path:
    return path or (metrics_dir() / _METRICS_FILENAME)


def record_turn(metrics: TurnMetrics, path: Path | None = None) -> None:
    """Append a turn's metrics as one JSON line. Best-effort — never raises.

    Analytics must never break a turn, so any I/O failure is logged at debug
    and swallowed.
    """
    try:
        target = _metrics_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(metrics.to_record()) + "\n")
    except Exception as exc:  # noqa: BLE001 — analytics is strictly non-critical
        logger.debug("Could not record turn metrics (non-fatal): {}", exc)


def load_recent(n: int = 20, path: Path | None = None) -> list[TurnMetrics]:
    """Return the most recent ``n`` turn-metric rows, newest last. Best-effort."""
    target = _metrics_path(path)
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []

    rows: list[TurnMetrics] = []
    for line in lines[-_MAX_ROWS:]:
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(TurnMetrics.from_record(json.loads(line)))
        except (json.JSONDecodeError, TypeError, ValueError):
            continue  # skip a corrupt row rather than fail the whole read
    return rows[-n:] if n > 0 else rows


def format_summary(records: list[TurnMetrics]) -> str:
    """Human-readable summary of recent turns. Pure — no I/O."""
    if not records:
        return "No turn metrics recorded yet."

    n = len(records)
    last = records[-1]

    def avg(select: Any) -> float:
        return sum(select(r) for r in records) / n

    slowest = max(r.total_seconds for r in records)

    lines = [
        f"Aradhya performance — last {n} turn{'s' if n != 1 else ''}",
        (
            f"  Last turn : total {last.total_seconds:5.1f}s  "
            f"(model {last.model_seconds:.1f}s · tools {last.tool_seconds:.1f}s · "
            f"overhead {last.overhead_seconds:.1f}s)  "
            f"iters {last.iterations}  tools {last.tool_calls}  "
            f"prompt {last.prompt_tokens} tok  gen {last.gen_tokens} tok"
            + (f"  reload {last.load_seconds:.1f}s" if last.load_seconds > 0.05 else "")
        ),
        (
            f"  Averages  : total {avg(lambda r: r.total_seconds):5.1f}s  "
            f"model {avg(lambda r: r.model_seconds):.1f}s  "
            f"tools {avg(lambda r: r.tool_seconds):.1f}s  "
            f"overhead {avg(lambda r: r.overhead_seconds):.1f}s  "
            f"iters {avg(lambda r: r.iterations):.1f}"
        ),
        f"  Slowest   : {slowest:.1f}s        Model: {last.model} ({last.provider})",
    ]
    return "\n".join(lines)
