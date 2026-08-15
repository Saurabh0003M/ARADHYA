"""Performance analytics for Aradhya.

A thin, append-only record of *where each turn's wall-clock actually went* —
total time split into model / tool / overhead, plus loop iterations and the
Ollama token counters. The point is to answer "why was that turn slow?" from
measurement instead of theory (the same discipline the Ollama timing logs
started). See :mod:`src.aradhya.analytics.turn_metrics`.
"""

from __future__ import annotations

from src.aradhya.analytics.turn_metrics import (
    TurnMetrics,
    format_summary,
    load_recent,
    record_turn,
)

__all__ = ["TurnMetrics", "format_summary", "load_recent", "record_turn"]
