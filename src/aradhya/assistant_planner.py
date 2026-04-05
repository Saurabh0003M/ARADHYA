"""Rule-based planner for Aradhya's current local assistant scope."""

from __future__ import annotations

import re

from src.aradhya.assistant_models import AssistantState, PlanAction, PlanKind
from src.aradhya.assistant_system_tools import SystemToolbox


class IntentPlanner:
    """Maps natural-language requests onto assistant plans."""

    def __init__(self, toolbox: SystemToolbox, now_provider):
        self.toolbox = toolbox
        self.now_provider = now_provider

    def build_plan(self, transcript: str, state: AssistantState) -> PlanAction:
        normalized = self._normalize_text(transcript)

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
