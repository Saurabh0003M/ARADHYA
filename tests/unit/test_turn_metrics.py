"""Unit tests for the per-turn performance analytics."""

from __future__ import annotations

import json

from src.aradhya.analytics.turn_metrics import (
    TurnMetrics,
    format_summary,
    load_recent,
    record_turn,
)


def _make(**overrides) -> TurnMetrics:
    base = dict(
        turn_id="t1",
        model="gemma4:e4b",
        provider="ollama",
        total_seconds=80.0,
        model_seconds=61.0,
        tool_seconds=3.0,
        iterations=3,
        tool_calls=2,
        prompt_tokens=5842,
        gen_tokens=210,
        load_seconds=0.0,
        success=True,
    )
    base.update(overrides)
    return TurnMetrics(**base)


def test_overhead_is_total_minus_model_and_tool():
    m = _make(total_seconds=80.0, model_seconds=61.0, tool_seconds=3.0)
    assert m.overhead_seconds == 80.0 - 61.0 - 3.0


def test_overhead_never_negative():
    # Clock skew or double-counting must not produce a negative overhead.
    m = _make(total_seconds=5.0, model_seconds=6.0, tool_seconds=2.0)
    assert m.overhead_seconds == 0.0


def test_record_round_trips_through_json():
    m = _make(load_seconds=12.34)
    record = m.to_record()
    # Computed field is included for at-a-glance reading of the raw log.
    assert record["overhead_seconds"] == 16.0
    # Survives a JSON encode/decode and rebuilds equal on the stored fields.
    restored = TurnMetrics.from_record(json.loads(json.dumps(record)))
    assert restored.turn_id == m.turn_id
    assert restored.model_seconds == m.model_seconds
    assert restored.prompt_tokens == m.prompt_tokens
    assert restored.load_seconds == 12.34


def test_from_record_ignores_unknown_and_computed_keys():
    row = {"turn_id": "x", "total_seconds": 10.0, "overhead_seconds": 7.0, "bogus": 1}
    m = TurnMetrics.from_record(row)
    assert m.turn_id == "x"
    assert m.total_seconds == 10.0
    # overhead is recomputed, not read from the stored (here stale) value
    assert m.overhead_seconds == 10.0


def test_record_and_load_recent_roundtrip(tmp_path):
    metrics_file = tmp_path / "turns.jsonl"
    for i in range(3):
        record_turn(_make(turn_id=f"t{i}", total_seconds=float(10 + i)), path=metrics_file)

    rows = load_recent(2, path=metrics_file)
    assert [r.turn_id for r in rows] == ["t1", "t2"]  # newest last, limited to 2
    assert rows[-1].total_seconds == 12.0


def test_load_recent_missing_file_is_empty(tmp_path):
    assert load_recent(5, path=tmp_path / "nope.jsonl") == []


def test_load_recent_skips_corrupt_rows(tmp_path):
    metrics_file = tmp_path / "turns.jsonl"
    metrics_file.write_text(
        json.dumps(_make(turn_id="good").to_record()) + "\n"
        + "{not valid json\n"
        + "\n",
        encoding="utf-8",
    )
    rows = load_recent(10, path=metrics_file)
    assert len(rows) == 1
    assert rows[0].turn_id == "good"


def test_record_turn_never_raises_on_bad_path(tmp_path):
    # A path whose parent is a file (not a dir) would fail mkdir; must be swallowed.
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    # Should not raise even though blocker/turns.jsonl is unwritable.
    record_turn(_make(), path=blocker / "turns.jsonl")


def test_format_summary_empty():
    assert "No turn metrics" in format_summary([])


def test_format_summary_contains_breakdown():
    out = format_summary([_make(total_seconds=80.0, model_seconds=61.0, tool_seconds=3.0)])
    assert "Last turn" in out
    assert "80.0s" in out
    assert "model 61.0s" in out
    assert "gemma4:e4b" in out
