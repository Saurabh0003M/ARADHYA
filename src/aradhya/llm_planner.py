"""LLM-assisted intent routing for Aradhya's safe planner."""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
import re
from typing import Any, Callable

from loguru import logger

from src.aradhya.assistant_models import AssistantState, PlanAction, PlanKind
from src.aradhya.assistant_system_tools import SystemToolbox
from src.aradhya.model_provider import TextModelProvider

LLM_CONFIDENCE_THRESHOLD = 0.65


@dataclass(frozen=True)
class LLMPlannerDecision:
    """Structured intent data extracted from the model response."""

    intent: str
    confidence: float
    reasoning: str
    target: str | None
    enabled: bool | None


class LLMIntentPlanner:
    """Uses the configured model provider for fallback intent classification.

    The model is never allowed to execute actions directly. It only classifies
    the request into a narrow JSON schema, and the existing toolbox still owns
    all filesystem resolution, previews, and execution safety.
    """

    def __init__(
        self,
        toolbox: SystemToolbox,
        model_provider: TextModelProvider,
        now_provider: Callable[[], Any],
    ):
        self.toolbox = toolbox
        self.model_provider = model_provider
        self.now_provider = now_provider

    def build_plan(self, transcript: str, state: AssistantState) -> PlanAction:
        try:
            raw_response = self.model_provider.generate(
                transcript,
                system_prompt=self._build_system_prompt(state),
            )
            decision = self._parse_decision(raw_response.text)
        except Exception as error:
            logger.warning("LLM planner failed for transcript '{}': {}", transcript, error)
            return PlanAction(
                kind=PlanKind.UNKNOWN,
                summary=(
                    "I could not safely classify that request with the configured local "
                    f"model. Details: {error}"
                ),
                requires_confirmation=False,
                ready=False,
            )

        logger.info(
            "LLM planner classified transcript '{}' as {} with confidence {}",
            transcript,
            decision.intent,
            decision.confidence,
        )

        if decision.confidence < LLM_CONFIDENCE_THRESHOLD:
            return PlanAction(
                kind=PlanKind.UNKNOWN,
                summary=(
                    "I asked the local reasoning model for help, but it was not "
                    f"confident enough to act safely ({decision.confidence:.2f})."
                ),
                requires_confirmation=False,
                ready=False,
                metadata={
                    "llm_intent": decision.intent,
                    "llm_confidence": decision.confidence,
                    "llm_reasoning": decision.reasoning,
                },
            )

        plan = self._route_decision(decision, transcript, state)
        return replace(
            plan,
            metadata={
                **plan.metadata,
                "llm_intent": decision.intent,
                "llm_confidence": decision.confidence,
                "llm_reasoning": decision.reasoning,
            },
        )

    def _build_system_prompt(self, state: AssistantState) -> str:
        debate_state = "enabled" if state.debate_mode_enabled else "disabled"
        return (
            "You are Aradhya's intent classifier. "
            "Return only valid JSON with these keys: "
            '"intent", "confidence", "reasoning", "target", "enabled". '
            "Do not return Markdown, code fences, shell commands, or extra text. "
            "Allowed intent values are: OPEN_PATH, OPEN_SECURITY_BLOGS, "
            "LOCATE_TXT_DENSE_FOLDER, OPEN_YESTERDAYS_PROJECT, OPEN_RECENT_GAME, "
            "SCREEN_CONTROL, EXTERNAL_DOCUMENT_HANDOFF, DEBATE_RESEARCH, "
            "TOGGLE_DEBATE, UNKNOWN. "
            "Use target only when the intent needs a path, app, or named thing. "
            "Use enabled only for TOGGLE_DEBATE. "
            "Be conservative: if you are unsure, return UNKNOWN or a confidence below 0.65. "
            f"The user's Debate AI mode is currently {debate_state}."
        )

    def _parse_decision(self, response_text: str) -> LLMPlannerDecision:
        match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if not match:
            raise ValueError("The model response did not contain valid JSON.")

        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid JSON from model: {error}") from error

        intent = str(payload.get("intent", "UNKNOWN")).upper().strip()
        confidence = self._coerce_confidence(payload.get("confidence"))
        reasoning = str(payload.get("reasoning", "")).strip()
        target = payload.get("target")
        enabled = self._coerce_enabled(payload.get("enabled"))

        if target is not None:
            target = str(target).strip() or None

        return LLMPlannerDecision(
            intent=intent,
            confidence=confidence,
            reasoning=reasoning,
            target=target,
            enabled=enabled,
        )

    def _route_decision(
        self,
        decision: LLMPlannerDecision,
        transcript: str,
        state: AssistantState,
    ) -> PlanAction:
        if decision.intent == "OPEN_PATH":
            if not decision.target:
                return self._unknown_missing_field("OPEN_PATH", "target")
            return self.toolbox.plan_open_path(decision.target)

        if decision.intent == "OPEN_SECURITY_BLOGS":
            return self.toolbox.plan_open_security_blogs()

        if decision.intent == "LOCATE_TXT_DENSE_FOLDER":
            return self.toolbox.plan_locate_txt_dense_folder()

        if decision.intent == "OPEN_YESTERDAYS_PROJECT":
            return self.toolbox.plan_open_yesterdays_project(self.now_provider())

        if decision.intent == "OPEN_RECENT_GAME":
            return self.toolbox.plan_open_recent_game()

        if decision.intent == "SCREEN_CONTROL":
            return self.toolbox.plan_screen_control(transcript)

        if decision.intent == "EXTERNAL_DOCUMENT_HANDOFF":
            return self.toolbox.plan_document_handoff(transcript)

        if decision.intent == "DEBATE_RESEARCH":
            if not state.debate_mode_enabled:
                return PlanAction(
                    kind=PlanKind.UNKNOWN,
                    summary=(
                        "The local model recognized this as a debate-style reasoning "
                        "request, but Debate AI mode is currently disabled."
                    ),
                    requires_confirmation=False,
                    ready=False,
                )
            return self.toolbox.plan_debate_research(transcript)

        if decision.intent == "TOGGLE_DEBATE":
            if decision.enabled is None:
                return self._unknown_missing_field("TOGGLE_DEBATE", "enabled")
            return self.toolbox.plan_toggle_debate(decision.enabled)

        return PlanAction(
            kind=PlanKind.UNKNOWN,
            summary=(
                "I asked the local reasoning model for help, but it routed the request "
                f"to an unsupported intent: {decision.intent}."
            ),
            requires_confirmation=False,
            ready=False,
        )

    def _coerce_confidence(self, raw_value: Any) -> float:
        try:
            return float(raw_value)
        except (TypeError, ValueError):
            raise ValueError("The model did not return a numeric confidence.")

    def _coerce_enabled(self, raw_value: Any) -> bool | None:
        if raw_value is None:
            return None
        if isinstance(raw_value, bool):
            return raw_value
        if isinstance(raw_value, str):
            normalized = raw_value.strip().lower()
            if normalized in {"true", "on", "enable", "enabled", "yes"}:
                return True
            if normalized in {"false", "off", "disable", "disabled", "no"}:
                return False
        raise ValueError("The model returned an invalid enabled value for TOGGLE_DEBATE.")

    def _unknown_missing_field(self, intent: str, field_name: str) -> PlanAction:
        return PlanAction(
            kind=PlanKind.UNKNOWN,
            summary=(
                f"The local reasoning model classified the request as {intent}, but it "
                f"did not provide the required '{field_name}' field."
            ),
            requires_confirmation=False,
            ready=False,
        )
