"""Planning workflow — complexity detection and structured plan generation.

When the agent receives a complex multi-step request, this module detects
it, generates a structured plan, and presents it for user approval before
execution.  Inspired by Antigravity's plan → approval → execution flow.

The workflow:
1. ``ComplexityDetector`` scores a request as simple vs complex
2. ``PlanGenerator`` uses the LLM to produce a structured ``TaskPlan``
3. The caller (``assistant_core``) stores the plan and asks for approval
4. On approval, steps are executed sequentially via the agent loop
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from loguru import logger

from src.aradhya.model_provider import TextModelProvider
from src.aradhya.utils.json_extractor import (
    JSONExtractionError,
    extract_json_from_llm_response,
)


# ── Data Models ───────────────────────────────────────────────────────

class PlanStepStatus(str, Enum):
    """Status of a single plan step."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PlanStep:
    """A single step in a structured task plan."""
    index: int
    title: str
    description: str
    tools_needed: list[str] = field(default_factory=list)
    status: PlanStepStatus = PlanStepStatus.PENDING
    result: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "title": self.title,
            "description": self.description,
            "tools_needed": self.tools_needed,
            "status": self.status.value,
            "result": self.result,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlanStep:
        return cls(
            index=data.get("index", 0),
            title=data.get("title", ""),
            description=data.get("description", ""),
            tools_needed=data.get("tools_needed", []),
            status=PlanStepStatus(data.get("status", "pending")),
            result=data.get("result", ""),
        )


@dataclass
class TaskPlan:
    """A structured multi-step plan for a complex request."""
    goal: str
    complexity_score: float
    reasoning: str
    steps: list[PlanStep] = field(default_factory=list)
    current_step: int = 0
    approved: bool = False

    @property
    def total_steps(self) -> int:
        return len(self.steps)

    @property
    def completed_steps(self) -> int:
        return sum(
            1 for s in self.steps
            if s.status in (PlanStepStatus.COMPLETED, PlanStepStatus.SKIPPED)
        )

    @property
    def is_complete(self) -> bool:
        return self.current_step >= self.total_steps

    @property
    def progress_summary(self) -> str:
        return f"{self.completed_steps}/{self.total_steps} steps complete"

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "complexity_score": self.complexity_score,
            "reasoning": self.reasoning,
            "steps": [s.to_dict() for s in self.steps],
            "current_step": self.current_step,
            "approved": self.approved,
        }

    def format_for_user(self) -> str:
        """Format the plan as a readable summary for user approval."""
        lines = [
            f"📋 **Plan: {self.goal}**",
            f"Complexity: {self.complexity_score:.0%} | {self.total_steps} steps",
            "",
        ]
        for step in self.steps:
            status_icon = {
                PlanStepStatus.PENDING: "⬜",
                PlanStepStatus.IN_PROGRESS: "🔄",
                PlanStepStatus.COMPLETED: "✅",
                PlanStepStatus.FAILED: "❌",
                PlanStepStatus.SKIPPED: "⏭️",
            }.get(step.status, "⬜")
            lines.append(f"{status_icon} **Step {step.index + 1}**: {step.title}")
            lines.append(f"   {step.description}")
            if step.tools_needed:
                lines.append(f"   Tools: {', '.join(step.tools_needed)}")
            lines.append("")

        lines.append(
            "Say **'yes proceed'** to execute this plan, or **'cancel'** to abort."
        )
        return "\n".join(lines)

    def get_next_step(self) -> PlanStep | None:
        """Return the next pending step, or None if all done."""
        if self.current_step < self.total_steps:
            return self.steps[self.current_step]
        return None

    def advance(self, result: str = "", success: bool = True) -> None:
        """Mark the current step as done and advance."""
        if self.current_step < self.total_steps:
            step = self.steps[self.current_step]
            step.status = (
                PlanStepStatus.COMPLETED if success else PlanStepStatus.FAILED
            )
            step.result = result
            self.current_step += 1


# ── Complexity Detector ───────────────────────────────────────────────

# Keywords that suggest a request is complex and needs planning
_COMPLEXITY_SIGNALS = (
    # Multi-step indicators
    "and then", "after that", "next", "finally", "first", "second",
    "step by step", "steps", "multiple",
    # Scope indicators
    "refactor", "redesign", "migrate", "rewrite", "restructure",
    "architecture", "overhaul", "integrate", "implement",
    # Analysis indicators
    "compare", "analyze", "evaluate", "research", "investigate",
    "all files", "entire", "whole project", "comprehensive",
    # Safety indicators (should plan before acting)
    "delete", "remove all", "replace all", "rename all",
    "production", "deploy", "database",
)

# Simple request patterns — should NOT trigger planning
_SIMPLICITY_SIGNALS = (
    "open", "show", "what is", "how to", "explain", "help",
    "list", "find", "search", "status", "hello", "hi",
    "toggle", "enable", "disable", "turn on", "turn off",
)

COMPLEXITY_THRESHOLD = 0.55


class ComplexityDetector:
    """Heuristic + optional LLM complexity scorer.

    Fast path: keyword analysis (no LLM call).
    Slow path: ask the model if the fast path is ambiguous (0.35-0.65 range).
    """

    def __init__(self, model_provider: TextModelProvider | None = None) -> None:
        self._model = model_provider

    def score(self, request: str) -> tuple[float, str]:
        """Return (complexity_score, reasoning) for a request.

        Score ∈ [0, 1]. Above ``COMPLEXITY_THRESHOLD`` → needs a plan.
        """
        heuristic_score, reasoning = self._heuristic_score(request)

        # If clearly simple or clearly complex, skip LLM
        if heuristic_score <= 0.30 or heuristic_score >= 0.70:
            return heuristic_score, reasoning

        # Ambiguous zone — use LLM if available
        if self._model is not None:
            try:
                llm_score, llm_reason = self._llm_score(request)
                # Blend: 40% heuristic + 60% LLM
                blended = 0.4 * heuristic_score + 0.6 * llm_score
                return blended, f"Heuristic: {reasoning}. LLM: {llm_reason}"
            except Exception as exc:
                logger.debug("LLM complexity scoring failed: {}", exc)

        return heuristic_score, reasoning

    def _heuristic_score(self, request: str) -> tuple[float, str]:
        """Keyword-based complexity estimation."""
        lower = request.lower()
        word_count = len(request.split())

        # Check simplicity signals first
        simple_hits = sum(1 for sig in _SIMPLICITY_SIGNALS if sig in lower)
        if simple_hits >= 2 and word_count < 15:
            return 0.15, f"Simple request ({simple_hits} simplicity signals)"

        # Count complexity signals
        complex_hits = sum(1 for sig in _COMPLEXITY_SIGNALS if sig in lower)

        # Length factor: longer requests tend to be more complex
        length_factor = min(word_count / 50.0, 1.0)

        # Multi-sentence bonus
        sentence_count = lower.count(".") + lower.count("?") + lower.count("!")
        sentence_factor = min(sentence_count / 3.0, 1.0) * 0.15

        # Combine signals
        signal_score = min(complex_hits / 3.0, 1.0) * 0.5
        score = signal_score + length_factor * 0.35 + sentence_factor
        score = min(max(score, 0.0), 1.0)

        return score, (
            f"{complex_hits} complexity signals, "
            f"{word_count} words, "
            f"{sentence_count} sentences"
        )

    def _llm_score(self, request: str) -> tuple[float, str]:
        """Ask the LLM to score complexity."""
        if self._model is None:
            raise RuntimeError("No model provider")

        result = self._model.generate(
            request,
            system_prompt=(
                "You are a task complexity evaluator. Given a user request, "
                "output ONLY valid JSON with two keys: "
                '"score" (float 0-1, where 0 is trivially simple and 1 is very complex), '
                '"reason" (brief explanation). '
                "A complex request involves multiple steps, file changes, "
                "architectural decisions, or careful planning. A simple request "
                "is a quick question, toggle, or single action."
            ),
        )

        payload = extract_json_from_llm_response(result.text)
        score = float(payload.get("score", 0.5))
        reason = str(payload.get("reason", ""))
        return score, reason


# ── Plan Generator ────────────────────────────────────────────────────

class PlanGenerator:
    """Uses the LLM to generate a structured TaskPlan."""

    def __init__(self, model_provider: TextModelProvider) -> None:
        self._model = model_provider

    def generate(self, request: str, complexity_score: float) -> TaskPlan:
        """Generate a TaskPlan from a complex user request."""
        try:
            result = self._model.generate(
                request,
                system_prompt=self._build_prompt(),
            )
            return self._parse_plan(result.text, request, complexity_score)
        except Exception as exc:
            logger.warning("Plan generation failed: {}", exc)
            # Fallback: create a single-step plan
            return TaskPlan(
                goal=request[:200],
                complexity_score=complexity_score,
                reasoning=f"Plan generation failed ({exc}); using single-step fallback.",
                steps=[
                    PlanStep(
                        index=0,
                        title="Execute request",
                        description=request,
                    )
                ],
            )

    def _build_prompt(self) -> str:
        return (
            "You are a task planner. Given a user request, break it down into "
            "a structured plan. Output ONLY valid JSON with these keys:\n"
            '- "goal": (string) A concise summary of the overall goal\n'
            '- "reasoning": (string) Why this plan was structured this way\n'
            '- "steps": (array of objects) Each step has:\n'
            '  - "title": (string) Short step title\n'
            '  - "description": (string) What to do in this step\n'
            '  - "tools_needed": (array of strings) Tool names this step might use '
            "(e.g., run_command, read_file, write_file, web_search, browser_open)\n\n"
            "Rules:\n"
            "- Keep steps atomic and actionable (2-8 steps typically)\n"
            "- Order steps logically (research before implementation)\n"
            "- Group related sub-tasks into single steps\n"
            "- Include verification/testing as a final step\n"
            "- Be specific about what each step accomplishes"
        )

    def _parse_plan(
        self,
        response: str,
        original_request: str,
        complexity_score: float,
    ) -> TaskPlan:
        """Parse LLM JSON response into a TaskPlan."""
        try:
            payload = extract_json_from_llm_response(response)
        except JSONExtractionError:
            raise ValueError(f"Could not extract JSON from plan response: {response[:200]}")

        goal = str(payload.get("goal", original_request[:200]))
        reasoning = str(payload.get("reasoning", ""))
        raw_steps = payload.get("steps", [])

        if not isinstance(raw_steps, list) or not raw_steps:
            raise ValueError("Plan has no steps")

        steps = []
        for i, raw in enumerate(raw_steps):
            if not isinstance(raw, dict):
                continue
            steps.append(PlanStep(
                index=i,
                title=str(raw.get("title", f"Step {i + 1}")),
                description=str(raw.get("description", "")),
                tools_needed=list(raw.get("tools_needed", [])),
            ))

        if not steps:
            raise ValueError("No valid steps parsed from plan")

        return TaskPlan(
            goal=goal,
            complexity_score=complexity_score,
            reasoning=reasoning,
            steps=steps,
        )
