"""Skill deduplication for Parasite OS host skills."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any, Callable

from loguru import logger

from src.aradhya.model_provider import TextModelProvider, build_text_model_provider
from src.aradhya.runtime_profile import load_runtime_profile
from src.aradhya.skills.skill_loader import _split_frontmatter, load_skills
from src.aradhya.skills.skill_models import SkillDefinition

# Use a type alias matching the project's ConfirmationGate protocol.
# The gate returns (approved: bool, persist: bool).
ConfirmationGate = Callable[[str, dict[str, Any]], tuple[bool, bool]]

# Keyword overlap thresholds for duplicate detection.
HOST_NATIVE_OVERLAP_THRESHOLD = 0.4
HOST_HOST_OVERLAP_THRESHOLD = 0.5


class SkillDeduplicator:
    """Identify and optionally merge overlapping host-generated skills."""

    def __init__(
        self,
        project_root: Path,
        *,
        provider: TextModelProvider | None = None,
        confirmation_gate: ConfirmationGate | None = None,
        audit_logger: Any | None = None,
    ) -> None:
        self.project_root = project_root
        self.confirmation_gate = confirmation_gate
        self.audit_logger = audit_logger
        if provider is None:
            profile = load_runtime_profile(project_root)
            provider = build_text_model_provider(profile.model)
        self.provider = provider

    def run_deduplication(self, *, dry_run: bool = True) -> list[dict[str, Any]]:
        """Return planned or completed deduplication actions.

        The default is read-only. Passing ``dry_run=False`` still requires a
        confirmation gate before any skill file is modified or directory is
        removed.
        """
        registry = load_skills(self.project_root)
        all_skills = registry.all_skills()
        host_skills = [skill for skill in all_skills if skill.name.startswith("host-")]
        native_skills = [skill for skill in all_skills if not skill.name.startswith("host-")]

        actions: list[dict[str, Any]] = []
        processed_duplicates: set[str] = set()
        for base, duplicate in self._find_candidate_pairs(native_skills, host_skills):
            if duplicate.name in processed_duplicates:
                continue
            if not self._llm_verify_duplicate(base, duplicate):
                continue

            action: dict[str, Any] = {
                "action": "merge",
                "base": base.name,
                "duplicate": duplicate.name,
                "dry_run": dry_run,
                "status": "planned" if dry_run else "pending",
            }
            if dry_run:
                actions.append(action)
                processed_duplicates.add(duplicate.name)
                continue

            if not self._confirm_merge(base, duplicate):
                action["status"] = "denied"
                actions.append(action)
                continue

            try:
                self._merge_skills(base, duplicate)
                action["status"] = "merged"
            except Exception as error:
                action["status"] = "error"
                action["error"] = str(error)
                logger.warning("Merge failed for {} into {}: {}", duplicate.name, base.name, error)
            actions.append(action)
            processed_duplicates.add(duplicate.name)
            self._audit_merge(action)

        return actions

    def _find_candidate_pairs(
        self,
        native_skills: list[SkillDefinition],
        host_skills: list[SkillDefinition],
    ) -> list[tuple[SkillDefinition, SkillDefinition]]:
        """Find likely duplicate skill pairs using deterministic keyword overlap."""
        pairs: list[tuple[SkillDefinition, SkillDefinition]] = []

        for host_skill in host_skills:
            host_words = self._skill_words(host_skill)
            if not host_words:
                continue

            best_match: SkillDefinition | None = None
            best_overlap = 0.0
            for native_skill in native_skills:
                native_words = self._skill_words(native_skill)
                if not native_words:
                    continue
                overlap = len(host_words & native_words) / min(
                    len(host_words),
                    len(native_words),
                )
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_match = native_skill

            if best_match is not None and best_overlap > HOST_NATIVE_OVERLAP_THRESHOLD:
                pairs.append((best_match, host_skill))

        for index, left in enumerate(host_skills):
            left_words = self._skill_words(left)
            if not left_words:
                continue
            for right in host_skills[index + 1:]:
                right_words = self._skill_words(right)
                if not right_words:
                    continue
                overlap = len(left_words & right_words) / min(
                    len(left_words),
                    len(right_words),
                )
                if overlap > HOST_HOST_OVERLAP_THRESHOLD:
                    pairs.append((left, right))

        return pairs

    @staticmethod
    def _skill_words(skill: SkillDefinition) -> set[str]:
        text = " ".join([skill.description, *skill.intents])
        return {
            word
            for word in re.findall(r"[a-z0-9][a-z0-9_-]{2,}", text.lower())
            if len(word) > 3
        }

    def _llm_verify_duplicate(
        self,
        skill_a: SkillDefinition,
        skill_b: SkillDefinition,
    ) -> bool:
        prompt = (
            "Are these two skills providing the same core capability?\n\n"
            f"Skill A ({skill_a.name}):\n"
            f"Description: {skill_a.description}\n"
            f"Intents: {', '.join(skill_a.intents)}\n\n"
            f"Skill B ({skill_b.name}):\n"
            f"Description: {skill_b.description}\n"
            f"Intents: {', '.join(skill_b.intents)}\n\n"
            "Reply with exactly MERGE or UNIQUE."
        )
        try:
            result = self.provider.generate(
                prompt,
                system_prompt="You are a strict deduplication AI. Output only MERGE or UNIQUE.",
            )
            return result.text.strip().upper().startswith("MERGE")
        except Exception as error:
            logger.warning("LLM verification failed for {} and {}: {}", skill_a.name, skill_b.name, error)
            return False

    def _confirm_merge(
        self,
        base: SkillDefinition,
        duplicate: SkillDefinition,
    ) -> bool:
        if self.confirmation_gate is None:
            logger.warning(
                "Refusing to merge {} into {} without a confirmation gate",
                duplicate.name,
                base.name,
            )
            return False
        approved, _persist = self.confirmation_gate(
            "parasite_dedup",
            {
                "operation": "merge_skill",
                "base": base.name,
                "duplicate": duplicate.name,
                "delete_dir": str(duplicate.base_dir),
            },
        )
        return approved

    def _merge_skills(
        self,
        base: SkillDefinition,
        duplicate: SkillDefinition,
    ) -> None:
        base_file = base.skill_file
        if not base_file.is_file():
            raise FileNotFoundError(f"Base skill file not found: {base_file}")

        merged_intents = self._dedupe_strings([*base.intents, *duplicate.intents])
        content = base_file.read_text(encoding="utf-8")
        content = self._replace_intents(content, merged_intents)
        self._validate_skill_content(content)
        base_file.write_text(content, encoding="utf-8")

        duplicate_dir = duplicate.base_dir.resolve()
        allowed_root = (self.project_root / "core" / "skills").resolve()
        if not duplicate.name.startswith("host-"):
            raise ValueError(f"Refusing to delete non-host skill: {duplicate.name}")
        if not self._is_relative_to(duplicate_dir, allowed_root):
            raise ValueError(f"Refusing to delete host skill outside core/skills: {duplicate_dir}")
        try:
            shutil.rmtree(duplicate_dir)
        except OSError as error:
            raise RuntimeError(
                f"Skill file updated but failed to delete duplicate dir {duplicate_dir}: {error}"
            ) from error
        logger.info("Merged {} into {} and deleted {}", duplicate.name, base.name, duplicate_dir)

    @staticmethod
    def _replace_intents(content: str, intents: list[str]) -> str:
        lines = content.splitlines()
        if not lines or lines[0].strip() != "---":
            raise ValueError("Skill file is missing YAML frontmatter")

        end_index = None
        for index in range(1, len(lines)):
            if lines[index].strip() == "---":
                end_index = index
                break
        if end_index is None:
            raise ValueError("Skill file frontmatter is not closed")

        frontmatter = lines[1:end_index]
        body = lines[end_index:]
        new_block = ["intents:", *[f"  - {SkillDeduplicator._clean_yaml_item(intent)}" for intent in intents]]

        start = None
        for index, line in enumerate(frontmatter):
            if line.startswith("intents:"):
                start = index
                break

        if start is None:
            frontmatter.extend(new_block)
        else:
            stop = start + 1
            while stop < len(frontmatter):
                line = frontmatter[stop]
                if line and not line.startswith(" "):
                    break
                stop += 1
            frontmatter = [*frontmatter[:start], *new_block, *frontmatter[stop:]]

        return "\n".join(["---", *frontmatter, *body]) + "\n"

    @staticmethod
    def _validate_skill_content(content: str) -> None:
        frontmatter, body = _split_frontmatter(content)
        if not body.strip():
            raise ValueError("Skill body is empty")
        intents = frontmatter.get("intents", [])
        if not isinstance(intents, list) or not intents:
            raise ValueError("Skill intents are invalid")

    @staticmethod
    def _clean_yaml_item(value: str) -> str:
        text = re.sub(r"[\r\n\t]+", " ", str(value))
        text = text.replace('"', "").replace("'", "")
        text = re.sub(r"\s+", " ", text).strip()
        return text or "reference material"

    @classmethod
    def _dedupe_strings(cls, values: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for value in values:
            cleaned = cls._clean_yaml_item(value)
            key = cleaned.lower()
            if key not in seen:
                seen.add(key)
                out.append(cleaned)
        return out

    @staticmethod
    def _is_relative_to(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    def _audit_merge(self, action: dict[str, Any]) -> None:
        audit = self.audit_logger
        if audit is None:
            from src.aradhya.audit_logger import get_audit_logger
            audit = get_audit_logger()
        audit.log_event("parasite_dedup_merge", action)
