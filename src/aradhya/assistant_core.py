"""Assistant orchestration layer for wake, planning, confirmation, and execution."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Callable

from loguru import logger

from src.aradhya.assistant_indexer import DirectoryIndexManager
from src.aradhya.assistant_models import (
    AssistantPreferences,
    AssistantResponse,
    AssistantState,
    PlanKind,
    ShellStateSnapshot,
    WakeSource,
    load_preferences,
)
from src.aradhya.assistant_planner import IntentPlanner
from src.aradhya.model_provider import TextModelProvider
from src.aradhya.assistant_system_tools import SystemToolbox


class AradhyaAssistant:
    """Stateful assistant core aligned to the updated Aradhya product spec."""

    def __init__(
        self,
        preferences: AssistantPreferences,
        model_provider: TextModelProvider | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ):
        self.preferences = preferences
        self.now_provider = now_provider or datetime.now
        self.state = AssistantState()
        self.index_manager = DirectoryIndexManager(
            preferences,
            now_provider=self.now_provider,
        )
        self.toolbox = SystemToolbox(preferences, self.index_manager)
        self.planner = IntentPlanner(
            self.toolbox,
            self.now_provider,
            model_provider=model_provider,
        )
        self._confirmation_phrases = {
            self._normalize_phrase(phrase)
            for phrase in self.preferences.confirmation_phrases
        }

    @classmethod
    def from_project_root(
        cls,
        project_root: Path | None = None,
        model_provider: TextModelProvider | None = None,
    ) -> "AradhyaAssistant":
        return cls(load_preferences(project_root), model_provider=model_provider)

    def handle_wake(self, source: WakeSource) -> AssistantResponse:
        self.state.is_awake = True
        self.state.pending_plan = None
        snapshot = None
        logger.info("Aradhya woke via {}", source.value)

        if self.preferences.directory_index_policy.refresh_on_wake:
            snapshot = self.index_manager.refresh_if_stale("wake")

        source_label = source.value.replace("_", " ")
        message = f"Aradhya is awake via {source_label}. Tell me what you want to do."
        if snapshot is not None:
            if snapshot.refreshed:
                message += " I refreshed the local directory index."
            else:
                message += " I reused the fresh local directory cache."

        return AssistantResponse(
            spoken_response=message,
            index_snapshot=snapshot,
        )

    def go_idle(self) -> AssistantResponse:
        self.state.is_awake = False
        self.state.pending_plan = None
        logger.info("Aradhya returned to idle state")
        return AssistantResponse(spoken_response="Aradhya is going idle.")

    def set_interaction_enabled(self, enabled: bool) -> ShellStateSnapshot:
        """Toggle whether user-level machine interaction is unlocked."""

        self.state.interaction_enabled = enabled
        return self.shell_state_snapshot()

    def arm_advanced_next_request(self) -> ShellStateSnapshot:
        """Enable one-shot advanced reasoning for the next planning request."""

        self.state.advanced_next_request = True
        return self.shell_state_snapshot()

    def set_screen_context_active(self, active: bool) -> ShellStateSnapshot:
        """Toggle bounded screen-guidance mode for shell requests."""

        self.state.screen_context_active = active
        return self.shell_state_snapshot()

    def set_cloud_features_enabled(self, enabled: bool) -> ShellStateSnapshot:
        """Toggle future opt-in cloud features for the current session."""

        self.state.cloud_features_enabled = enabled
        return self.shell_state_snapshot()

    def shell_state_snapshot(self) -> ShellStateSnapshot:
        """Return the shell-visible state so UI code can render controls."""

        return ShellStateSnapshot(
            interaction_enabled=self.state.interaction_enabled,
            advanced_next_request=self.state.advanced_next_request,
            screen_context_active=self.state.screen_context_active,
            cloud_features_enabled=self.state.cloud_features_enabled,
        )

    def handle_transcript(self, transcript: str) -> AssistantResponse:
        logger.info("Handling transcript: {}", transcript)
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
            logger.info("Canceled pending plan after transcript '{}'", transcript)
            return AssistantResponse(
                spoken_response="I canceled the pending task.",
                transcript_echo=transcript,
            )

        if self.state.pending_plan and self._is_confirmation_phrase(normalized):
            plan = self.state.pending_plan
            if self.toolbox.requires_admin_permission(plan):
                logger.info(
                    "Blocked confirmed plan {} because separate admin approval is required",
                    plan.kind,
                )
                return AssistantResponse(
                    spoken_response=(
                        "This task still requires separate admin approval. "
                        "Elevation is not wired in yet."
                    ),
                    transcript_echo=transcript,
                    plan=plan,
                    awaiting_confirmation=True,
                    index_snapshot=self.index_manager.last_snapshot,
                )

            if self.toolbox.requires_interaction_permission(plan) and not self.state.interaction_enabled:
                logger.info(
                    "Blocked confirmed plan {} because interaction is locked",
                    plan.kind,
                )
                return AssistantResponse(
                    spoken_response=(
                        "Interaction is locked. Turn on I to allow machine actions, "
                        "then confirm again."
                    ),
                    transcript_echo=transcript,
                    plan=plan,
                    awaiting_confirmation=True,
                    index_snapshot=self.index_manager.last_snapshot,
                )

            self.state.pending_plan = None
            # Execution happens only after an explicit confirmation phrase,
            # which is the main safety barrier in the current assistant.
            result = self.toolbox.execute(plan, self.state)
            logger.info("Executed confirmed plan {} with success={}", plan.kind, result.success)
            return AssistantResponse(
                spoken_response=result.message,
                transcript_echo=transcript,
                plan=plan,
                result=result,
            )

        replacing_pending = self.state.pending_plan is not None
        advanced_reasoning = self.state.advanced_next_request
        if advanced_reasoning:
            self.state.advanced_next_request = False

        plan = self.planner.build_plan(
            transcript,
            self.state,
            advanced_reasoning=advanced_reasoning,
        )
        self.state.pending_plan = None

        snapshot = None
        if (
            plan.uses_local_data
            and self.preferences.directory_index_policy.refresh_on_local_query
        ):
            snapshot = self.index_manager.last_snapshot

        if plan.kind == PlanKind.UNKNOWN or not plan.ready:
            logger.info("Planner returned non-executable plan {}", plan.kind)
            return AssistantResponse(
                spoken_response=plan.summary,
                transcript_echo=transcript,
                plan=plan,
                index_snapshot=snapshot,
            )

        if plan.requires_confirmation:
            # The pending plan is stored here so the next "yes proceed" can
            # execute exactly this action and not a newer transcript.
            self.state.pending_plan = plan
            logger.info("Stored pending plan {} awaiting confirmation", plan.kind)
            prefix = "I replaced the earlier pending task. " if replacing_pending else ""
            if self.toolbox.requires_admin_permission(plan):
                guidance = "This task needs separate admin approval before it can run."
            elif self.toolbox.requires_interaction_permission(plan) and not self.state.interaction_enabled:
                guidance = "Interaction is locked. Turn on I, then say 'yes proceed' to execute it."
            else:
                guidance = "Say 'yes proceed' when you want me to execute it."
            return AssistantResponse(
                spoken_response=(
                    f"{prefix}{plan.summary} {guidance}"
                ),
                transcript_echo=transcript,
                plan=plan,
                awaiting_confirmation=True,
                index_snapshot=snapshot,
            )

        result = self.toolbox.execute(plan, self.state)
        logger.info("Executed immediate plan {} with success={}", plan.kind, result.success)
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
        return normalized in {
            "cancel",
            "stop",
            "never mind",
            "nevermind",
            "no",
            "no thanks",
            "dont do it",
            "do not do it",
            "no cancel",
        }
