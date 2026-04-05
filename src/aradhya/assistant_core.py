"""Assistant orchestration layer for wake, planning, confirmation, and execution."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Callable

from src.aradhya.assistant_indexer import DirectoryIndexManager
from src.aradhya.assistant_models import (
    AssistantPreferences,
    AssistantResponse,
    AssistantState,
    PlanKind,
    WakeSource,
    load_preferences,
)
from src.aradhya.assistant_planner import IntentPlanner
from src.aradhya.assistant_system_tools import SystemToolbox


class AradhyaAssistant:
    """Stateful assistant core aligned to the updated Aradhya product spec."""

    def __init__(
        self,
        preferences: AssistantPreferences,
        now_provider: Callable[[], datetime] | None = None,
    ):
        self.preferences = preferences
        self.now_provider = now_provider or datetime.now
        self.state = AssistantState()
        self.index_manager = DirectoryIndexManager(preferences)
        self.toolbox = SystemToolbox(preferences)
        self.planner = IntentPlanner(self.toolbox, self.now_provider)
        self._confirmation_phrases = {
            self._normalize_phrase(phrase)
            for phrase in self.preferences.confirmation_phrases
        }

    @classmethod
    def from_project_root(cls, project_root: Path | None = None) -> "AradhyaAssistant":
        return cls(load_preferences(project_root))

    def handle_wake(self, source: WakeSource) -> AssistantResponse:
        self.state.is_awake = True
        self.state.pending_plan = None
        snapshot = None

        if self.preferences.directory_index_policy.refresh_on_wake:
            snapshot = self.index_manager.refresh("wake")

        source_label = source.value.replace("_", " ")
        message = f"Aradhya is awake via {source_label}. Tell me what you want to do."
        if snapshot is not None:
            message += " I refreshed the local directory index."

        return AssistantResponse(
            spoken_response=message,
            index_snapshot=snapshot,
        )

    def go_idle(self) -> AssistantResponse:
        self.state.is_awake = False
        self.state.pending_plan = None
        return AssistantResponse(spoken_response="Aradhya is going idle.")

    def handle_transcript(self, transcript: str) -> AssistantResponse:
        if not self.state.is_awake:
            return AssistantResponse(
                spoken_response=(
                    "Wake me first with the floating icon or the Ctrl plus Win shortcut."
                ),
                transcript_echo=transcript,
            )

        normalized = self._normalize_phrase(transcript)
        if not normalized:
            return AssistantResponse(
                spoken_response="I did not catch any usable speech in that transcript.",
                transcript_echo=transcript,
            )

        if self.state.pending_plan and self._is_cancel_phrase(normalized):
            self.state.pending_plan = None
            return AssistantResponse(
                spoken_response="I canceled the pending task.",
                transcript_echo=transcript,
            )

        if self.state.pending_plan and self._is_confirmation_phrase(normalized):
            plan = self.state.pending_plan
            self.state.pending_plan = None
            result = self.toolbox.execute(plan, self.state)
            return AssistantResponse(
                spoken_response=result.message,
                transcript_echo=transcript,
                plan=plan,
                result=result,
            )

        replacing_pending = self.state.pending_plan is not None
        plan = self.planner.build_plan(transcript, self.state)
        self.state.pending_plan = None

        snapshot = None
        if (
            plan.uses_local_data
            and self.preferences.directory_index_policy.refresh_on_local_query
        ):
            snapshot = self.index_manager.refresh("local_query")

        if plan.kind == PlanKind.UNKNOWN or not plan.ready:
            return AssistantResponse(
                spoken_response=plan.summary,
                transcript_echo=transcript,
                plan=plan,
                index_snapshot=snapshot,
            )

        if plan.requires_confirmation:
            self.state.pending_plan = plan
            prefix = "I replaced the earlier pending task. " if replacing_pending else ""
            return AssistantResponse(
                spoken_response=(
                    f"{prefix}{plan.summary} Say 'yes proceed' when you want me "
                    "to execute it."
                ),
                transcript_echo=transcript,
                plan=plan,
                awaiting_confirmation=True,
                index_snapshot=snapshot,
            )

        result = self.toolbox.execute(plan, self.state)
        return AssistantResponse(
            spoken_response=result.message,
            transcript_echo=transcript,
            plan=plan,
            result=result,
            index_snapshot=snapshot,
        )

    def _normalize_phrase(self, phrase: str) -> str:
        return " ".join(re.findall(r"[a-z0-9]+", phrase.lower()))

    def _is_confirmation_phrase(self, normalized: str) -> bool:
        return normalized in self._confirmation_phrases

    def _is_cancel_phrase(self, normalized: str) -> bool:
        return normalized in {"cancel", "stop", "never mind", "nevermind", "no cancel"}
