"""Cloud/local model worker registry.

This is an offline registry.  It reports which workers are configured and
whether the needed environment variables are visible, but it does not perform
network calls.  Live cloud probes should stay behind an explicit user action.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from src.aradhya.providers.openrouter import FREE_MODELS
from src.aradhya.runtime_profile import RuntimeProfile, build_default_runtime_profile


MODEL_WORKERS_FILENAME = "model_workers.json"
MODEL_WORKERS_LOCAL_FILENAME = "model_workers.local.json"


@dataclass(frozen=True)
class ModelWorker:
    """A single local or optional cloud model worker."""

    worker_id: str
    role: str
    provider: str
    model_name: str
    privacy_mode: str
    tier: str
    context_tokens: int
    description: str
    enabled: bool = True
    api_key_env: str = ""
    owner: str = "aradhya"


@dataclass(frozen=True)
class ModelWorkerStatus:
    """Offline readiness for one worker."""

    worker: ModelWorker
    key_present: bool
    status: str
    detail: str


class ModelWorkerRegistry:
    """Build model worker status from defaults plus optional local config."""

    def __init__(self, project_root: Path, runtime_profile: RuntimeProfile) -> None:
        self.project_root = project_root
        self.runtime_profile = runtime_profile

    def workers(self) -> list[ModelWorker]:
        workers = self._default_workers()
        return self._apply_config_overrides(workers)

    def statuses(self) -> list[ModelWorkerStatus]:
        statuses: list[ModelWorkerStatus] = []
        for worker in self.workers():
            key_present = bool(worker.api_key_env and os.environ.get(worker.api_key_env))
            if not worker.enabled:
                status = "disabled"
                detail = "Defined but disabled in configuration."
            elif worker.provider == "ollama":
                status = "local"
                detail = "Local worker; no cloud key needed."
            elif worker.api_key_env and key_present:
                status = "configured"
                detail = f"Cloud key is visible via {worker.api_key_env}."
            elif worker.api_key_env:
                status = "needs_env"
                detail = (
                    f"{worker.api_key_env} is not visible to this process. "
                    "Open a new terminal after setx if you just created it."
                )
            else:
                status = "needs_key"
                detail = "Cloud worker has no api_key_env configured."

            statuses.append(
                ModelWorkerStatus(
                    worker=worker,
                    key_present=key_present,
                    status=status,
                    detail=detail,
                )
            )
        return statuses

    def get_worker(self, worker_id: str) -> ModelWorker | None:
        normalized = worker_id.strip().lower()
        for worker in self.workers():
            if worker.worker_id.lower() == normalized:
                return worker
        return None

    def _default_workers(self) -> list[ModelWorker]:
        workers: list[ModelWorker] = []

        current = self.runtime_profile.model
        current_privacy = "local-only" if current.provider.lower() == "ollama" else "public-cloud-only"
        current_tier = "local" if current.provider.lower() == "ollama" else "cloud"
        workers.append(
            ModelWorker(
                worker_id="configured-primary",
                role="primary",
                provider=current.provider,
                model_name=current.model_name,
                privacy_mode=current_privacy,
                tier=current_tier,
                context_tokens=0,
                description="The model currently used by Aradhya.",
                api_key_env=current.api_key_env if current.provider.lower() != "ollama" else "",
            )
        )

        local_fallback = self._local_fallback_model_name()
        if current.provider.lower() != "ollama":
            workers.append(
                ModelWorker(
                    worker_id="local-fallback",
                    role="fallback_local",
                    provider="ollama",
                    model_name=local_fallback,
                    privacy_mode="local-only",
                    tier="local",
                    context_tokens=0,
                    description="Local Ollama fallback for private prompts.",
                )
            )

        workers.extend(
            [
                self._openrouter_worker(
                    "cloud-balanced",
                    "balanced",
                    "google/gemma-4-31b-it:free",
                    "General cloud-safe reasoning and multilingual work.",
                ),
                self._openrouter_worker(
                    "cloud-planner",
                    "planning",
                    "nvidia/nemotron-3-super:free",
                    "Long-context planning and roadmap digestion.",
                ),
                self._openrouter_worker(
                    "cloud-coder",
                    "coding",
                    "poolside/laguna-m.1:free",
                    "Coding-oriented agent work on public snippets.",
                ),
                self._openrouter_worker(
                    "cloud-reviewer",
                    "review",
                    "arcee-ai/trinity-large-thinking:free",
                    "Reasoning-heavy review of non-private artifacts.",
                ),
                self._openrouter_worker(
                    "cloud-fast",
                    "fast",
                    "openai/gpt-oss-20b:free",
                    "Low-latency cloud-safe drafts and summaries.",
                ),
                self._openrouter_worker(
                    "cloud-long-context",
                    "long_context",
                    "deepseek/deepseek-v4-flash:free",
                    "Large public context windows and coding triage.",
                ),
                self._openrouter_worker(
                    "opus-collaborator",
                    "parallel_agent",
                    "google/gemma-4-31b-it:free",
                    "Separate OpenRouter key intended for the parallel Opus worker.",
                    api_key_env="OPUS_OPENROUTER_API_KEY",
                    owner="opus",
                ),
            ]
        )
        return self._dedupe(workers)

    def _openrouter_worker(
        self,
        worker_id: str,
        role: str,
        model_name: str,
        description: str,
        *,
        api_key_env: str = "ARADHYA_OPENROUTER_API_KEY",
        owner: str = "aradhya",
    ) -> ModelWorker:
        info = FREE_MODELS.get(model_name, {})
        return ModelWorker(
            worker_id=worker_id,
            role=role,
            provider="openrouter",
            model_name=model_name,
            privacy_mode="public-cloud-only",
            tier=str(info.get("tier", "cloud")),
            context_tokens=int(info.get("context", 0) or 0),
            description=description,
            api_key_env=api_key_env,
            owner=owner,
        )

    def _local_fallback_model_name(self) -> str:
        shared_profile = self.project_root / "core" / "config" / "profile.json"
        try:
            payload = json.loads(shared_profile.read_text(encoding="utf-8"))
            raw_model = payload.get("model", {})
            if isinstance(raw_model, dict) and raw_model.get("provider") == "ollama":
                model_name = str(raw_model.get("model_name", "")).strip()
                if model_name:
                    return model_name
        except (OSError, json.JSONDecodeError):
            pass
        return build_default_runtime_profile(self.project_root).model.model_name

    def _apply_config_overrides(self, workers: list[ModelWorker]) -> list[ModelWorker]:
        by_id = {worker.worker_id: worker for worker in workers}
        for path in self._config_paths():
            payload = self._load_payload(path)
            for raw_worker in payload.get("workers", []):
                if not isinstance(raw_worker, dict):
                    continue
                worker_id = str(raw_worker.get("worker_id") or raw_worker.get("id") or "").strip()
                if not worker_id:
                    continue
                existing = by_id.get(worker_id)
                if existing is None:
                    by_id[worker_id] = self._worker_from_payload(raw_worker)
                else:
                    by_id[worker_id] = self._merge_worker(existing, raw_worker)
        return list(by_id.values())

    def _config_paths(self) -> tuple[Path, Path]:
        config_dir = self.project_root / "core" / "config"
        return config_dir / MODEL_WORKERS_FILENAME, config_dir / MODEL_WORKERS_LOCAL_FILENAME

    def _load_payload(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _worker_from_payload(self, payload: dict[str, Any]) -> ModelWorker:
        worker_id = str(payload.get("worker_id") or payload.get("id") or "custom-worker")
        return ModelWorker(
            worker_id=worker_id,
            role=str(payload.get("role", "custom")),
            provider=str(payload.get("provider", "openrouter")),
            model_name=str(payload.get("model_name", "")),
            privacy_mode=str(payload.get("privacy_mode", "public-cloud-only")),
            tier=str(payload.get("tier", "custom")),
            context_tokens=int(payload.get("context_tokens", 0) or 0),
            description=str(payload.get("description", "")),
            enabled=bool(payload.get("enabled", True)),
            api_key_env=str(payload.get("api_key_env", "")),
            owner=str(payload.get("owner", "aradhya")),
        )

    def _merge_worker(self, worker: ModelWorker, payload: dict[str, Any]) -> ModelWorker:
        allowed = {
            "role",
            "provider",
            "model_name",
            "privacy_mode",
            "tier",
            "context_tokens",
            "description",
            "enabled",
            "api_key_env",
            "owner",
        }
        updates = {key: payload[key] for key in allowed if key in payload}
        if "context_tokens" in updates:
            updates["context_tokens"] = int(updates["context_tokens"] or 0)
        if "enabled" in updates:
            updates["enabled"] = bool(updates["enabled"])
        return replace(worker, **updates)

    def _dedupe(self, workers: list[ModelWorker]) -> list[ModelWorker]:
        seen: set[str] = set()
        unique: list[ModelWorker] = []
        for worker in workers:
            if worker.worker_id in seen:
                continue
            seen.add(worker.worker_id)
            unique.append(worker)
        return unique
