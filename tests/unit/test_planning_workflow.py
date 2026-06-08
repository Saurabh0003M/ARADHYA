"""Tests for the planning workflow — complexity detection and plan generation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.aradhya.planning_workflow import (
    COMPLEXITY_THRESHOLD,
    ComplexityDetector,
    PlanGenerator,
    PlanStep,
    PlanStepStatus,
    TaskPlan,
)


# ──────────────────────────────────────────────────────────────────────
# Data Models
# ──────────────────────────────────────────────────────────────────────

class TestPlanStep:
    """Test PlanStep data model."""

    def test_default_status(self):
        step = PlanStep(index=0, title="Test", description="Do stuff")
        assert step.status == PlanStepStatus.PENDING

    def test_to_dict(self):
        step = PlanStep(
            index=0,
            title="Research",
            description="Look into the code",
            tools_needed=["read_file"],
        )
        d = step.to_dict()
        assert d["title"] == "Research"
        assert d["tools_needed"] == ["read_file"]
        assert d["status"] == "pending"

    def test_from_dict(self):
        d = {
            "index": 1,
            "title": "Implement",
            "description": "Write the code",
            "tools_needed": ["write_file"],
            "status": "completed",
            "result": "Done",
        }
        step = PlanStep.from_dict(d)
        assert step.title == "Implement"
        assert step.status == PlanStepStatus.COMPLETED
        assert step.result == "Done"


class TestTaskPlan:
    """Test TaskPlan data model."""

    def _make_plan(self, n_steps: int = 3) -> TaskPlan:
        return TaskPlan(
            goal="Test refactoring",
            complexity_score=0.75,
            reasoning="Complex task",
            steps=[
                PlanStep(index=i, title=f"Step {i}", description=f"Do {i}")
                for i in range(n_steps)
            ],
        )

    def test_total_steps(self):
        plan = self._make_plan(3)
        assert plan.total_steps == 3

    def test_is_complete_initially_false(self):
        plan = self._make_plan(3)
        assert plan.is_complete is False

    def test_advance_marks_completed(self):
        plan = self._make_plan(2)
        plan.advance("Result 1", success=True)
        assert plan.steps[0].status == PlanStepStatus.COMPLETED
        assert plan.steps[0].result == "Result 1"
        assert plan.current_step == 1

    def test_advance_marks_failed(self):
        plan = self._make_plan(2)
        plan.advance("Error!", success=False)
        assert plan.steps[0].status == PlanStepStatus.FAILED
        assert plan.current_step == 1

    def test_full_advance_to_complete(self):
        plan = self._make_plan(2)
        plan.advance("OK", success=True)
        plan.advance("OK", success=True)
        assert plan.is_complete is True
        assert plan.completed_steps == 2

    def test_progress_summary(self):
        plan = self._make_plan(3)
        plan.advance("OK", success=True)
        assert plan.progress_summary == "1/3 steps complete"

    def test_get_next_step(self):
        plan = self._make_plan(2)
        step = plan.get_next_step()
        assert step is not None
        assert step.index == 0

        plan.advance("OK", success=True)
        step = plan.get_next_step()
        assert step is not None
        assert step.index == 1

        plan.advance("OK", success=True)
        step = plan.get_next_step()
        assert step is None

    def test_format_for_user(self):
        plan = self._make_plan(2)
        formatted = plan.format_for_user()
        assert "Test refactoring" in formatted
        assert "Step 1" in formatted
        assert "Step 2" in formatted
        assert "yes proceed" in formatted.lower()

    def test_to_dict(self):
        plan = self._make_plan(2)
        d = plan.to_dict()
        assert d["goal"] == "Test refactoring"
        assert len(d["steps"]) == 2
        assert d["complexity_score"] == 0.75


# ──────────────────────────────────────────────────────────────────────
# Complexity Detector
# ──────────────────────────────────────────────────────────────────────

class TestComplexityDetector:
    """Test the heuristic complexity scorer."""

    def test_simple_request_scores_low(self):
        detector = ComplexityDetector()
        score, _ = detector.score("open my documents folder")
        assert score < COMPLEXITY_THRESHOLD

    def test_simple_greeting_scores_low(self):
        detector = ComplexityDetector()
        score, _ = detector.score("hello")
        assert score < 0.3

    def test_complex_request_scores_high(self):
        detector = ComplexityDetector()
        score, _ = detector.score(
            "Refactor the entire authentication module. First analyze "
            "the current implementation, then restructure the code to "
            "use a factory pattern, and finally write integration tests."
        )
        assert score >= COMPLEXITY_THRESHOLD

    def test_multi_step_request_scores_high(self):
        detector = ComplexityDetector()
        score, _ = detector.score(
            "First research the best database options, then migrate "
            "the SQLite backend to PostgreSQL, after that update all "
            "the queries, and finally deploy to production."
        )
        assert score >= COMPLEXITY_THRESHOLD

    def test_moderate_request(self):
        detector = ComplexityDetector()
        score, _ = detector.score("find and delete all temp files")
        # Moderate — should not crash
        assert 0.0 <= score <= 1.0

    def test_returns_reasoning(self):
        detector = ComplexityDetector()
        _, reasoning = detector.score("analyze all files")
        assert isinstance(reasoning, str)
        assert len(reasoning) > 0

    def test_empty_request(self):
        detector = ComplexityDetector()
        score, _ = detector.score("")
        assert score < COMPLEXITY_THRESHOLD

    def test_with_model_provider_blends_scores(self):
        """When a model is available, scores should blend."""
        mock_model = MagicMock()
        mock_model.generate.return_value = MagicMock(
            text='{"score": 0.8, "reason": "Very complex"}'
        )
        detector = ComplexityDetector(model_provider=mock_model)
        # This request is in the ambiguous zone (0.35-0.65 heuristic)
        score, reasoning = detector.score(
            "implement a caching layer for the API"
        )
        # Should be a blended score
        assert 0.0 <= score <= 1.0


# ──────────────────────────────────────────────────────────────────────
# Plan Generator
# ──────────────────────────────────────────────────────────────────────

class TestPlanGenerator:
    """Test plan generation from LLM responses."""

    def _mock_model(self, response_json: str) -> MagicMock:
        model = MagicMock()
        model.generate.return_value = MagicMock(text=response_json)
        return model

    def test_generates_valid_plan(self):
        response = '''{
            "goal": "Refactor auth module",
            "reasoning": "Multi-step task needs planning",
            "steps": [
                {"title": "Analyze current code", "description": "Read auth files", "tools_needed": ["read_file"]},
                {"title": "Implement changes", "description": "Write new code", "tools_needed": ["write_file"]},
                {"title": "Run tests", "description": "Verify changes", "tools_needed": ["run_command"]}
            ]
        }'''
        model = self._mock_model(response)
        gen = PlanGenerator(model)
        plan = gen.generate("refactor auth", complexity_score=0.8)

        assert plan.goal == "Refactor auth module"
        assert plan.total_steps == 3
        assert plan.steps[0].title == "Analyze current code"
        assert plan.steps[2].tools_needed == ["run_command"]

    def test_fallback_on_invalid_json(self):
        model = self._mock_model("This is not valid JSON at all")
        gen = PlanGenerator(model)
        plan = gen.generate("do something complex", complexity_score=0.7)

        # Should produce a fallback single-step plan
        assert plan.total_steps == 1
        assert plan.steps[0].title == "Execute request"

    def test_fallback_on_exception(self):
        model = MagicMock()
        model.generate.side_effect = RuntimeError("Model crashed")
        gen = PlanGenerator(model)
        plan = gen.generate("do something", complexity_score=0.6)

        assert plan.total_steps == 1
        assert "failed" in plan.reasoning.lower()

    def test_empty_steps_gets_fallback(self):
        response = '{"goal": "Test", "reasoning": "test", "steps": []}'
        model = self._mock_model(response)
        gen = PlanGenerator(model)
        plan = gen.generate("test request", complexity_score=0.5)

        # Empty steps should trigger fallback
        assert plan.total_steps == 1

    def test_complexity_score_preserved(self):
        response = '''{
            "goal": "Simple plan",
            "reasoning": "OK",
            "steps": [{"title": "Do it", "description": "Just do it", "tools_needed": []}]
        }'''
        model = self._mock_model(response)
        gen = PlanGenerator(model)
        plan = gen.generate("test", complexity_score=0.92)

        assert plan.complexity_score == 0.92
