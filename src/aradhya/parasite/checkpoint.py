"""Checkpoint persistence for crash-resilient digestion.

Each digestion target gets a checkpoint file at:
    Hosts/<target>/.parasite/checkpoint.json

If the agent is terminated mid-pipeline, ``load_checkpoint`` reads
the last completed stage so ``pipeline.resume()`` can skip ahead.

Modeled after Antigravity's own brain/<uuid>/ persistence pattern.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

# GitHub token expires 30 days from creation (2026-05-19).
# Renew by ~2026-06-18 at https://github.com/settings/tokens
GITHUB_TOKEN_EXPIRY_NOTE = "Token created 2026-05-19, expires ~2026-06-18"

PARASITE_DIR = ".parasite"
CHECKPOINT_FILENAME = "checkpoint.json"

STAGES = (
    "DISCOVER",
    "VERIFY",
    "ISOLATE",
    "ANALYZE",
    "INTEGRATE",
    "VALIDATE",
    "ABSORB",
)


@dataclass
class StageResult:
    """Outcome of one pipeline stage."""

    stage: str
    status: str  # "completed", "failed", "skipped"
    started_at: str = ""
    completed_at: str = ""
    error: str = ""
    artifacts: dict[str, Any] = field(default_factory=dict)


@dataclass
class Checkpoint:
    """Full checkpoint state for one digestion target."""

    target: str
    source_url: str = ""
    current_stage: str = "DISCOVER"
    completed_stages: list[str] = field(default_factory=list)
    stage_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    started_at: str = ""
    last_checkpoint: str = ""
    trust_score: str = ""  # LOW / MEDIUM / HIGH / VERIFIED
    error: str = ""


def checkpoint_dir(hosts_root: Path, target: str) -> Path:
    """Return the .parasite directory for a target."""
    return hosts_root / target / PARASITE_DIR


def checkpoint_path(hosts_root: Path, target: str) -> Path:
    """Return the checkpoint.json path for a target."""
    return checkpoint_dir(hosts_root, target) / CHECKPOINT_FILENAME


def load_checkpoint(hosts_root: Path, target: str) -> Checkpoint | None:
    """Load checkpoint from disk.  Returns None if no checkpoint exists."""
    path = checkpoint_path(hosts_root, target)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    return Checkpoint(
        target=str(raw.get("target", target)),
        source_url=str(raw.get("source_url", "")),
        current_stage=str(raw.get("current_stage", "DISCOVER")),
        completed_stages=list(raw.get("completed_stages", [])),
        stage_results=dict(raw.get("stage_results", {})),
        started_at=str(raw.get("started_at", "")),
        last_checkpoint=str(raw.get("last_checkpoint", "")),
        trust_score=str(raw.get("trust_score", "")),
        error=str(raw.get("error", "")),
    )


def save_checkpoint(hosts_root: Path, cp: Checkpoint) -> Path:
    """Persist checkpoint to disk.  Creates directories if needed."""
    cp.last_checkpoint = _now()
    path = checkpoint_path(hosts_root, cp.target)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(cp), indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return path


def record_stage_start(cp: Checkpoint, stage: str) -> None:
    """Mark a stage as in-progress."""
    cp.current_stage = stage
    cp.stage_results[stage] = {
        "stage": stage,
        "status": "running",
        "started_at": _now(),
    }


def record_stage_complete(
    cp: Checkpoint,
    stage: str,
    *,
    artifacts: dict[str, Any] | None = None,
) -> None:
    """Mark a stage as completed."""
    result = cp.stage_results.get(stage, {"stage": stage, "started_at": _now()})
    result["status"] = "completed"
    result["completed_at"] = _now()
    if artifacts:
        result["artifacts"] = artifacts
    cp.stage_results[stage] = result
    if stage not in cp.completed_stages:
        cp.completed_stages.append(stage)


def record_stage_failure(cp: Checkpoint, stage: str, error: str) -> None:
    """Mark a stage as failed."""
    result = cp.stage_results.get(stage, {"stage": stage, "started_at": _now()})
    result["status"] = "failed"
    result["completed_at"] = _now()
    result["error"] = error
    cp.stage_results[stage] = result
    cp.error = error


def next_stage(cp: Checkpoint) -> str | None:
    """Return the next stage to run, or None if all are done."""
    for stage in STAGES:
        if stage not in cp.completed_stages:
            return stage
    return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
