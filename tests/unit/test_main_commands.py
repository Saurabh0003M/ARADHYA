from __future__ import annotations

from src.aradhya import main
from src.aradhya.runtime_profile import build_default_runtime_profile


def test_dispatch_model_workers_command(monkeypatch, tmp_path):
    captured = {}

    def fake_render(statuses):
        captured["count"] = len(statuses)

    monkeypatch.setattr(main, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(main, "render_model_workers", fake_render)

    handled = main._dispatch_command(
        "/model workers",
        runtime_profile=build_default_runtime_profile(tmp_path),
    )

    assert handled is True
    assert captured["count"] > 1


def test_dispatch_model_workers_assess_command(monkeypatch, tmp_path):
    captured = {}

    def fake_render(assessment):
        captured["allowed"] = assessment.allowed

    monkeypatch.setattr(main, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(main, "render_cloud_safety_assessment", fake_render)

    handled = main._dispatch_command(
        "/model workers assess summarize public API docs",
        runtime_profile=build_default_runtime_profile(tmp_path),
    )

    assert handled is True
    assert captured["allowed"] is True


def test_dispatch_apis_search_command(monkeypatch, tmp_path):
    captured = {}

    def fake_render(title, entries, risk_labels):
        captured["title"] = title
        captured["names"] = [entry.name for entry in entries]
        captured["risks"] = risk_labels

    monkeypatch.setattr(main, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(main, "render_api_entries", fake_render)

    handled = main._dispatch_command("/apis search weather")

    assert handled is True
    assert "Open-Meteo" in captured["names"]
    assert captured["risks"]["Open-Meteo"] == "low: no auth + HTTPS"
