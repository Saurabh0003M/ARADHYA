"""P0-4: skill intents emitted by the LLM classifier must route to an
AGENT_TASK (so the matching skill actually runs) instead of falling through
to the 'unsupported intent' UNKNOWN branch."""

from __future__ import annotations

from pathlib import Path

from src.aradhya.assistant_models import AssistantState, PlanKind
from src.aradhya.llm_planner import LLMIntentPlanner
from src.aradhya.model_provider import ModelResult
from src.aradhya.skills.skill_models import SkillDefinition, SkillRegistry


class FakeModelProvider:
    def __init__(self, response_text: str) -> None:
        self.response_text = response_text

    def generate(self, prompt: str, *, system_prompt: str | None = None) -> ModelResult:
        return ModelResult(
            text=self.response_text,
            model="fake-model",
            provider="fake",
            raw={},
        )


class _UnusedToolbox:
    """The skill-intent branch returns without touching the toolbox; any call
    here would be a regression, so fail loudly."""

    def __getattr__(self, name):
        raise AssertionError(f"toolbox.{name} should not be called for a skill intent")


def _registry_with_skill(intent: str) -> SkillRegistry:
    registry = SkillRegistry()
    registry.register(
        SkillDefinition(
            name="jobs",
            description="Help find government jobs.",
            instructions="Search official portals and summarize openings.",
            base_dir=Path("."),
            intents=(intent,),
        )
    )
    return registry


def _planner(response_text: str, registry: SkillRegistry | None) -> LLMIntentPlanner:
    return LLMIntentPlanner(
        toolbox=_UnusedToolbox(),
        model_provider=FakeModelProvider(response_text),
        now_provider=lambda: None,
        skill_registry=registry,
    )


def test_skill_intent_routes_to_agent_task():
    registry = _registry_with_skill("FIND_JOBS")
    planner = _planner(
        '{"intent": "FIND_JOBS", "confidence": 0.9, "reasoning": "wants jobs", '
        '"target": null, "enabled": null}',
        registry,
    )

    plan = planner.build_plan("find me government jobs", AssistantState())

    assert plan.kind == PlanKind.AGENT_TASK
    assert plan.metadata["request"] == "find me government jobs"
    assert plan.metadata["route_reason"] == "skill_intent:FIND_JOBS"


def test_skill_intent_matches_case_insensitively():
    # SKILL.md declares a lowercase intent; the classifier upper-cases it.
    registry = _registry_with_skill("find_jobs")
    planner = _planner(
        '{"intent": "FIND_JOBS", "confidence": 0.9, "reasoning": "wants jobs", '
        '"target": null, "enabled": null}',
        registry,
    )

    plan = planner.build_plan("find me government jobs", AssistantState())

    assert plan.kind == PlanKind.AGENT_TASK


def test_unknown_non_skill_intent_still_unknown():
    registry = _registry_with_skill("FIND_JOBS")
    planner = _planner(
        '{"intent": "DO_SOMETHING_ELSE", "confidence": 0.9, "reasoning": "?", '
        '"target": null, "enabled": null}',
        registry,
    )

    plan = planner.build_plan("please do something weird", AssistantState())

    assert plan.kind == PlanKind.UNKNOWN


def test_skill_intent_without_registry_is_unknown():
    planner = _planner(
        '{"intent": "FIND_JOBS", "confidence": 0.9, "reasoning": "wants jobs", '
        '"target": null, "enabled": null}',
        None,
    )

    plan = planner.build_plan("find me government jobs", AssistantState())

    assert plan.kind == PlanKind.UNKNOWN
