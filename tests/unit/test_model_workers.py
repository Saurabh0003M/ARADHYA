from __future__ import annotations

import json

from src.aradhya.model_workers import ModelWorkerRegistry
from src.aradhya.runtime_profile import build_default_runtime_profile


def test_model_worker_registry_reports_local_and_cloud_workers(tmp_path, monkeypatch):
    monkeypatch.delenv("ARADHYA_OPENROUTER_API_KEY", raising=False)
    profile = build_default_runtime_profile(tmp_path)

    statuses = ModelWorkerRegistry(tmp_path, profile).statuses()
    by_id = {status.worker.worker_id: status for status in statuses}

    assert by_id["configured-primary"].status == "local"
    assert by_id["cloud-balanced"].status == "needs_env"
    assert by_id["cloud-balanced"].worker.model_name == "google/gemma-4-31b-it:free"


def test_model_worker_registry_detects_visible_openrouter_key(tmp_path, monkeypatch):
    monkeypatch.setenv("ARADHYA_OPENROUTER_API_KEY", "test-key")
    profile = build_default_runtime_profile(tmp_path)

    statuses = ModelWorkerRegistry(tmp_path, profile).statuses()
    by_id = {status.worker.worker_id: status for status in statuses}

    assert by_id["cloud-balanced"].status == "configured"
    assert by_id["cloud-balanced"].key_present is True


def test_model_worker_registry_applies_local_overrides(tmp_path, monkeypatch):
    monkeypatch.delenv("ARADHYA_OPENROUTER_API_KEY", raising=False)
    config_dir = tmp_path / "core" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "model_workers.local.json").write_text(
        json.dumps(
            {
                "workers": [
                    {
                        "worker_id": "cloud-balanced",
                        "enabled": False,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    profile = build_default_runtime_profile(tmp_path)

    statuses = ModelWorkerRegistry(tmp_path, profile).statuses()
    by_id = {status.worker.worker_id: status for status in statuses}

    assert by_id["cloud-balanced"].status == "disabled"
