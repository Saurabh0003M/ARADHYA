"""Planning previews and safe execution helpers for system-level tasks."""

from __future__ import annotations

import os
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path

from src.aradhya.assistant_indexer import DirectoryIndexManager
from src.aradhya.assistant_models import (
    AssistantPreferences,
    AssistantState,
    ExecutionResult,
    PlanAction,
    PlanKind,
)


class SystemToolbox:
    """Contains the local heuristics that back Aradhya's plans."""

    def __init__(
        self,
        preferences: AssistantPreferences,
        index_manager: DirectoryIndexManager,
    ):
        self.preferences = preferences
        self.index_manager = index_manager

    def plan_open_path(self, query: str) -> PlanAction:
        matches = self.index_manager.find_named_paths(query, limit=5, reason="local_query")
        if not matches:
            return PlanAction(
                kind=PlanKind.OPEN_PATH,
                summary=(
                    f"I searched your configured roots but could not find a path "
                    f"matching '{query}'."
                ),
                requires_confirmation=False,
                uses_local_data=True,
                ready=False,
                metadata={"query": query},
            )

        best_match = max(matches, key=lambda path: self._score_path(path, query))
        return PlanAction(
            kind=PlanKind.OPEN_PATH,
            summary=f"I found the strongest match for '{query}' at {best_match}.",
            uses_local_data=True,
            metadata={"query": query, "target": str(best_match)},
        )

    def plan_open_security_blogs(self) -> PlanAction:
        urls = tuple(self.preferences.security_blog_urls)
        if not urls:
            return PlanAction(
                kind=PlanKind.OPEN_SECURITY_BLOGS,
                summary="Security blog preferences are empty, so there is nothing to open yet.",
                requires_confirmation=False,
                ready=False,
            )

        return PlanAction(
            kind=PlanKind.OPEN_SECURITY_BLOGS,
            summary=(
                "I am ready to open your preferred security blogs: "
                + ", ".join(urls)
                + "."
            ),
            metadata={"urls": list(urls)},
        )

    def plan_locate_txt_dense_folder(self) -> PlanAction:
        candidate = self.index_manager.find_txt_dense_folder(reason="local_query")
        if candidate is None:
            return PlanAction(
                kind=PlanKind.LOCATE_TXT_DENSE_FOLDER,
                summary="I could not find any visible folder containing .txt files.",
                requires_confirmation=False,
                uses_local_data=True,
                ready=False,
            )

        folder_path, txt_count, density = candidate
        return PlanAction(
            kind=PlanKind.LOCATE_TXT_DENSE_FOLDER,
            summary=(
                f"The strongest .txt-heavy folder looks like {folder_path} with "
                f"{txt_count} .txt files and {density:.0%} text density."
            ),
            uses_local_data=True,
            metadata={
                "target": str(folder_path),
                "txt_count": txt_count,
                "density": density,
            },
        )

    def plan_open_yesterdays_project(self, now: datetime) -> PlanAction:
        candidate = self.index_manager.find_yesterdays_project(now, reason="local_query")
        if candidate is None:
            yesterday = self._yesterday_label(now)
            return PlanAction(
                kind=PlanKind.OPEN_YESTERDAYS_PROJECT,
                summary=(
                    f"I did not find a project with clear activity markers on {yesterday}."
                ),
                requires_confirmation=False,
                uses_local_data=True,
                ready=False,
            )

        project_path, activity_time = candidate
        return PlanAction(
            kind=PlanKind.OPEN_YESTERDAYS_PROJECT,
            summary=(
                f"Your most active project from yesterday appears to be {project_path}, "
                f"last touched at {activity_time.isoformat(timespec='seconds')}."
            ),
            uses_local_data=True,
            metadata={"target": str(project_path)},
        )

    def plan_open_recent_game(self) -> PlanAction:
        candidate = self.index_manager.find_recent_game(reason="local_query")
        if candidate is None:
            return PlanAction(
                kind=PlanKind.OPEN_RECENT_GAME,
                summary=(
                    "I do not have enough game-library metadata yet to identify a recent "
                    "game. Populate 'game_library_roots' in preferences first."
                ),
                requires_confirmation=False,
                uses_local_data=True,
                ready=False,
            )

        game_path, activity_time = candidate
        return PlanAction(
            kind=PlanKind.OPEN_RECENT_GAME,
            summary=(
                f"The best recent-game match is {game_path}, last updated at "
                f"{activity_time.isoformat(timespec='seconds')}."
            ),
            uses_local_data=True,
            metadata={"target": str(game_path)},
        )

    def plan_screen_control(self, transcript: str) -> PlanAction:
        return PlanAction(
            kind=PlanKind.SCREEN_CONTROL,
            summary=(
                "I can recognize this as an on-screen control task, but the vision and "
                "UI automation adapter for Meet controls is not wired into this repo yet."
            ),
            requires_confirmation=False,
            ready=False,
            metadata={"request": transcript},
        )

    def plan_document_handoff(self, transcript: str) -> PlanAction:
        return PlanAction(
            kind=PlanKind.EXTERNAL_DOCUMENT_HANDOFF,
            summary=(
                "This sounds like a large-document or file-transformation task. The "
                "external AI handoff workflow is planned, but the browser/upload bridge "
                "is not implemented in this codebase yet."
            ),
            requires_confirmation=False,
            external_handoff=True,
            ready=False,
            metadata={"request": transcript},
        )

    def plan_debate_research(self, transcript: str) -> PlanAction:
        return PlanAction(
            kind=PlanKind.DEBATE_RESEARCH,
            summary=(
                "Debate mode is enabled, so I would route this through the multi-model "
                "debate workflow. The provider fan-out and consensus loop are still pending."
            ),
            requires_confirmation=False,
            external_handoff=True,
            ready=False,
            metadata={"request": transcript},
        )

    def plan_toggle_debate(self, enabled: bool) -> PlanAction:
        state_label = "enabled" if enabled else "disabled"
        return PlanAction(
            kind=PlanKind.TOGGLE_DEBATE,
            summary=f"I am ready to set Debate AI mode to {state_label}.",
            # Debate mode changes only Aradhya's internal routing state, so it
            # can execute immediately without opening apps, files, or URLs.
            requires_confirmation=False,
            metadata={"enabled": enabled},
        )

    def execute(self, plan: PlanAction, state: AssistantState) -> ExecutionResult:
        if plan.kind == PlanKind.TOGGLE_DEBATE:
            enabled = bool(plan.metadata.get("enabled"))
            state.debate_mode_enabled = enabled
            label = "enabled" if enabled else "disabled"
            return ExecutionResult(True, f"Debate AI mode is now {label}.")

        if plan.kind == PlanKind.OPEN_SECURITY_BLOGS:
            urls = tuple(plan.metadata.get("urls", []))
            if not urls:
                return ExecutionResult(False, "No security blog URLs are configured.")

            if self.preferences.allow_live_execution:
                for url in urls:
                    webbrowser.open_new_tab(url)
                return ExecutionResult(
                    True,
                    "Opened your preferred security blogs in the browser.",
                    artifacts=urls,
                )

            return ExecutionResult(
                True,
                "Dry run: I would open your preferred security blogs.",
                artifacts=urls,
            )

        if plan.kind in {
            PlanKind.OPEN_PATH,
            PlanKind.LOCATE_TXT_DENSE_FOLDER,
            PlanKind.OPEN_YESTERDAYS_PROJECT,
            PlanKind.OPEN_RECENT_GAME,
        }:
            target = plan.metadata.get("target")
            if not target:
                return ExecutionResult(False, "This plan does not have a target to open.")

            if self.preferences.allow_live_execution and hasattr(os, "startfile"):
                os.startfile(target)  # type: ignore[attr-defined]
                return ExecutionResult(
                    True,
                    f"Opened {target}.",
                    artifacts=(target,),
                )

            return ExecutionResult(
                True,
                f"Dry run: I would open {target}.",
                artifacts=(target,),
            )

        return ExecutionResult(
            False,
            "This plan is recognized, but its executor is not implemented yet.",
        )

    def _score_path(self, path: Path, query: str) -> float:
        score = 0.0
        lowered_path = str(path).lower()
        lowered_name = path.name.lower()
        lowered_query = query.lower()

        if lowered_name == lowered_query:
            score += 1.0
        elif lowered_query in lowered_name:
            score += 0.5

        if path.is_dir():
            score += 0.4

        if path.suffix.lower() == ".lnk":
            score -= 0.2

        if lowered_path.startswith("f:\\"):
            score += 0.3

        if "appdata" in lowered_path:
            score -= 0.5

        score += max(0.0, 0.3 - len(path.parts) * 0.02)
        return score

    def _yesterday_label(self, now: datetime) -> str:
        return (now - timedelta(days=1)).date().isoformat()
