"""Planning previews and safe execution helpers for system-level tasks."""

from __future__ import annotations

import os
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path

from src.aradhya.assistant_models import (
    AssistantPreferences,
    AssistantState,
    ExecutionResult,
    PlanAction,
    PlanKind,
)


class SystemToolbox:
    """Contains the local heuristics that back Aradhya's plans."""

    def __init__(self, preferences: AssistantPreferences):
        self.preferences = preferences
        self._ignored_names = {
            name.lower() for name in preferences.directory_index_policy.ignored_names
        }

    def plan_open_path(self, query: str) -> PlanAction:
        matches = self._search_named_paths(query)
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
        candidate = self._find_txt_dense_folder()
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
        candidate = self._find_yesterdays_project(now)
        if candidate is None:
            yesterday = (now - timedelta(days=1)).date().isoformat()
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
        candidate = self._find_recent_game()
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

    def _search_named_paths(self, query: str, limit: int = 5) -> list[Path]:
        normalized_query = query.lower()
        matches: list[Path] = []

        for root in self.preferences.user_roots:
            if not root.exists():
                continue

            for current_root, dirnames, filenames in os.walk(
                root,
                topdown=True,
                onerror=lambda _error: None,
            ):
                dirnames[:] = [
                    dirname
                    for dirname in dirnames
                    if not self._should_ignore_name(dirname)
                ]

                current_path = Path(current_root)
                if normalized_query in current_path.name.lower():
                    matches.append(current_path)
                    if len(matches) >= limit:
                        return matches

                for filename in filenames:
                    if self._should_ignore_name(filename):
                        continue

                    if normalized_query in filename.lower():
                        matches.append(current_path / filename)
                        if len(matches) >= limit:
                            return matches

        return matches

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

    def _find_txt_dense_folder(self) -> tuple[Path, int, float] | None:
        best_candidate: tuple[Path, int, float] | None = None
        best_score: tuple[int, float, int] | None = None

        for root in self.preferences.user_roots:
            if not root.exists():
                continue

            for current_root, dirnames, filenames in os.walk(
                root,
                topdown=True,
                onerror=lambda _error: None,
            ):
                dirnames[:] = [
                    dirname
                    for dirname in dirnames
                    if not self._should_ignore_name(dirname)
                ]
                visible_files = [
                    filename
                    for filename in filenames
                    if not self._should_ignore_name(filename)
                ]
                if not visible_files:
                    continue

                txt_count = sum(
                    1
                    for filename in visible_files
                    if Path(filename).suffix.lower() == ".txt"
                )
                if txt_count == 0:
                    continue

                density = txt_count / len(visible_files)
                current_path = Path(current_root)
                score = (txt_count, density, -len(current_path.parts))

                if best_score is None or score > best_score:
                    best_score = score
                    best_candidate = (current_path, txt_count, density)

        return best_candidate

    def _find_yesterdays_project(
        self,
        now: datetime,
    ) -> tuple[Path, datetime] | None:
        target_day = (now - timedelta(days=1)).date()
        marker_names = {marker.lower() for marker in self.preferences.project_markers}
        best_candidate: tuple[Path, datetime] | None = None

        for root in self.preferences.user_roots:
            if not root.exists():
                continue

            for current_root, dirnames, filenames in os.walk(
                root,
                topdown=True,
                onerror=lambda _error: None,
            ):
                dirnames[:] = [
                    dirname
                    for dirname in dirnames
                    if not self._should_ignore_name(dirname)
                ]

                if not any(filename.lower() in marker_names for filename in filenames):
                    continue

                project_path = Path(current_root)
                activity_time = self._estimate_project_activity(project_path)
                if activity_time is None or activity_time.date() != target_day:
                    continue

                if best_candidate is None or activity_time > best_candidate[1]:
                    best_candidate = (project_path, activity_time)

        return best_candidate

    def _estimate_project_activity(self, project_path: Path) -> datetime | None:
        latest_timestamp = self._safe_timestamp(project_path)
        files_seen = 0
        max_files = 500
        max_depth = 3

        for current_root, dirnames, filenames in os.walk(
            project_path,
            topdown=True,
            onerror=lambda _error: None,
        ):
            current_path = Path(current_root)
            depth = len(current_path.relative_to(project_path).parts)
            if depth >= max_depth:
                dirnames[:] = []
            else:
                dirnames[:] = [
                    dirname
                    for dirname in dirnames
                    if not self._should_ignore_name(dirname)
                ]

            for filename in filenames:
                if self._should_ignore_name(filename):
                    continue

                candidate_timestamp = self._safe_timestamp(current_path / filename)
                if candidate_timestamp is not None:
                    latest_timestamp = max(
                        latest_timestamp or candidate_timestamp,
                        candidate_timestamp,
                    )

                files_seen += 1
                if files_seen >= max_files:
                    break

            if files_seen >= max_files:
                break

        if latest_timestamp is None:
            return None

        return datetime.fromtimestamp(latest_timestamp)

    def _find_recent_game(self) -> tuple[Path, datetime] | None:
        if not self.preferences.game_library_roots:
            return None

        blocked_tokens = ("crash", "unins", "setup", "redistributable")
        best_candidate: tuple[Path, datetime] | None = None

        for root in self.preferences.game_library_roots:
            if not root.exists():
                continue

            for current_root, dirnames, filenames in os.walk(
                root,
                topdown=True,
                onerror=lambda _error: None,
            ):
                dirnames[:] = [
                    dirname
                    for dirname in dirnames
                    if not self._should_ignore_name(dirname)
                ]

                for filename in filenames:
                    lowered_name = filename.lower()
                    if self._should_ignore_name(filename):
                        continue
                    if not lowered_name.endswith((".exe", ".lnk")):
                        continue
                    if any(token in lowered_name for token in blocked_tokens):
                        continue

                    candidate_path = Path(current_root) / filename
                    timestamp = self._safe_timestamp(candidate_path)
                    if timestamp is None:
                        continue

                    candidate = (candidate_path, datetime.fromtimestamp(timestamp))
                    if best_candidate is None or candidate[1] > best_candidate[1]:
                        best_candidate = candidate

        return best_candidate

    def _safe_timestamp(self, path: Path) -> float | None:
        try:
            return path.stat().st_mtime
        except OSError:
            return None

    def _should_ignore_name(self, name: str) -> bool:
        return name.lower() in self._ignored_names
