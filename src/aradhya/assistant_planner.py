"""Hybrid planner that prefers fast local rules before LLM fallback."""

from __future__ import annotations

import re
from typing import Callable

from loguru import logger

from src.aradhya.assistant_models import AssistantState, PlanAction, PlanKind
from src.aradhya.assistant_system_tools import SystemToolbox
from src.aradhya.llm_planner import LLMIntentPlanner
from src.aradhya.model_provider import TextModelProvider
from src.aradhya.skills.skill_models import SkillRegistry


class IntentPlanner:
    """Maps natural-language requests onto safe assistant plans.

    The planner keeps the existing deterministic routes for crisp commands such
    as ``open Notes`` or ``enable debate mode``. When those rules do not match,
    it can ask the configured local model to classify the request into a narrow
    JSON schema that still routes back through the same safe toolbox methods.
    """

    def __init__(
        self,
        toolbox: SystemToolbox,
        now_provider: Callable,
        model_provider: TextModelProvider | None = None,
        skill_registry: SkillRegistry | None = None,
    ):
        self.toolbox = toolbox
        self.now_provider = now_provider
        self.skill_registry = skill_registry
        self.llm_planner = (
            LLMIntentPlanner(
                toolbox, model_provider, now_provider,
                skill_registry=skill_registry,
            )
            if model_provider is not None
            else None
        )

    def build_plan(self, transcript: str, state: AssistantState) -> PlanAction:
        normalized = self._normalize_text(transcript)
        # Fast local matches stay first so exact commands remain responsive and
        # predictable even when the model is unavailable.
        rule_based_plan = self._build_rule_based_plan(transcript, normalized, state)
        if rule_based_plan is not None:
            return rule_based_plan

        if self.llm_planner is not None:
            logger.info("No rule matched transcript '{}'; using LLM fallback planner.", transcript)
            llm_plan = self.llm_planner.build_plan(transcript, state)
            if llm_plan.kind != PlanKind.UNKNOWN and llm_plan.ready:
                return llm_plan
            return self._build_agent_task_plan(
                transcript,
                route_reason=llm_plan.summary,
            )

        return PlanAction(
            kind=PlanKind.UNKNOWN,
            summary=(
                "I can currently plan system tasks like opening paths, finding .txt-heavy "
                "folders, reopening yesterday's project, opening security blogs, and "
                "toggling Debate AI mode."
            ),
            requires_confirmation=False,
            ready=False,
        )

    def _build_agent_task_plan(
        self,
        transcript: str,
        *,
        route_reason: str = "",
    ) -> PlanAction:
        return PlanAction(
            kind=PlanKind.AGENT_TASK,
            summary=(
                "I can work on this as a model-driven agent task. I will let the "
                "backend model choose read/search tools, inspect results, and stop "
                "with a final answer. Machine-changing tools stay policy-gated."
            ),
            requires_confirmation=True,
            metadata={
                "request": transcript,
                "route_reason": route_reason,
            },
        )

    def _build_rule_based_plan(
        self,
        transcript: str,
        normalized: str,
        state: AssistantState,
    ) -> PlanAction | None:
        if self._is_toggle_debate_request(normalized, enable=True):
            return self.toolbox.plan_toggle_debate(True)

        if self._is_toggle_debate_request(normalized, enable=False):
            return self.toolbox.plan_toggle_debate(False)

        if self._is_screen_control_request(normalized):
            return self.toolbox.plan_screen_control(transcript)

        if self._is_document_handoff_request(normalized):
            return self.toolbox.plan_document_handoff(transcript)

        if self._is_security_blog_request(normalized):
            return self.toolbox.plan_open_security_blogs()

        if self._is_txt_folder_request(normalized):
            return self.toolbox.plan_locate_txt_dense_folder()

        if self._is_yesterdays_project_request(normalized):
            return self.toolbox.plan_open_yesterdays_project(self.now_provider())

        if self._is_recent_game_request(normalized):
            return self.toolbox.plan_open_recent_game()

        if state.debate_mode_enabled and self._is_research_request(normalized):
            return self.toolbox.plan_debate_research(transcript)

        if normalized.startswith("open "):
            return self.toolbox.plan_open_path(transcript[5:].strip())

        return None

    def _normalize_text(self, text: str) -> str:
        return " ".join(re.findall(r"[a-z0-9+.]+", text.lower()))

    def _is_toggle_debate_request(self, normalized: str, enable: bool) -> bool:
        if enable:
            return any(
                phrase in normalized
                for phrase in (
                    "enable debate",
                    "turn on debate",
                    "enable debate ai",
                    "turn on debate ai",
                )
            )

        return any(
            phrase in normalized
            for phrase in (
                "disable debate",
                "turn off debate",
                "disable debate ai",
                "turn off debate ai",
            )
        )

    def _is_screen_control_request(self, normalized: str) -> bool:
        meet_terms = ("meet", "google meet")
        control_terms = ("camera", "mic", "microphone", "screen share", "screenshare")
        return any(term in normalized for term in meet_terms) and any(
            term in normalized for term in control_terms
        )

    def _is_document_handoff_request(self, normalized: str) -> bool:
        file_terms = (".pdf", ".doc", ".docx", ".ppt", ".pptx")
        action_terms = (
            "summarize",
            "analyze",
            "analysis",
            "questions",
            "convert",
            "invert",
        )
        return any(term in normalized for term in file_terms) and any(
            term in normalized for term in action_terms
        )

    def _is_security_blog_request(self, normalized: str) -> bool:
        return "security blog" in normalized or "security blogs" in normalized

    def _is_txt_folder_request(self, normalized: str) -> bool:
        txt_terms = ("txt", ".txt")
        folder_terms = ("folder", "directory")
        density_terms = (
            "highest concentration",
            "most",
            "highest number",
            "txt heavy",
        )
        return any(term in normalized for term in txt_terms) and any(
            term in normalized for term in folder_terms
        ) and any(term in normalized for term in density_terms)

    def _is_yesterdays_project_request(self, normalized: str) -> bool:
        return "yesterday" in normalized and "project" in normalized

    def _is_recent_game_request(self, normalized: str) -> bool:
        return any(
            phrase in normalized
            for phrase in (
                "recently played game",
                "most recently played game",
                "last played game",
            )
        )

    def _is_research_request(self, normalized: str) -> bool:
        research_terms = (
            "research",
            "reason",
            "investigate",
            "compare",
            "best option",
            "what should",
            "which should",
        )
        return any(term in normalized for term in research_terms)
