"""Digestion pipeline — the core of Parasite OS.

Orchestrates the 7-stage pipeline:
    ENGULF → ISOLATE → CHEW → SWALLOW → DIGEST → EXTRACT → ABSORB

Each stage writes a checkpoint so the pipeline can resume after any
termination (crash, high traffic, user Ctrl+C).
"""

from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from src.aradhya.parasite.checkpoint import (
    Checkpoint,
    load_checkpoint,
    next_stage,
    record_stage_complete,
    record_stage_failure,
    record_stage_start,
    save_checkpoint,
)
from src.aradhya.parasite.analyzer import (
    analyze_target,
    analyze_public_apis_readme,
    generate_digest,
)
from src.aradhya.cloud_safety import CloudPrivacyGate


class DigestionPipeline:
    """Runs a target through the 7-stage digestion pipeline."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.hosts_root = project_root / "Hosts"
        self.privacy_gate = CloudPrivacyGate()

    def list_targets(self) -> list[dict[str, Any]]:
        """List all targets in Hosts/ with their pipeline status."""
        targets: list[dict[str, Any]] = []
        if not self.hosts_root.is_dir():
            return targets

        for child in sorted(self.hosts_root.iterdir()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            cp = load_checkpoint(self.hosts_root, child.name)
            targets.append({
                "name": child.name,
                "current_stage": cp.current_stage if cp else "NOT_STARTED",
                "completed_stages": cp.completed_stages if cp else [],
                "trust_score": cp.trust_score if cp else "",
                "error": cp.error if cp else "",
            })
        return targets

    def digest(self, target: str, *, source_url: str = "") -> Checkpoint:
        """Run the full pipeline on a target.  Resumes from last checkpoint."""
        target_path = self.hosts_root / target

        # Load or create checkpoint
        cp = load_checkpoint(self.hosts_root, target)
        if cp is None:
            cp = Checkpoint(
                target=target,
                source_url=source_url,
            )
            from src.aradhya.parasite.checkpoint import _now
            cp.started_at = _now()

        logger.info("Digestion pipeline: target={}, resuming from={}", target, cp.current_stage)

        # Run each incomplete stage
        while True:
            stage = next_stage(cp)
            if stage is None:
                logger.info("All stages complete for {}", target)
                break

            logger.info("Running stage {} for {}", stage, target)
            record_stage_start(cp, stage)
            save_checkpoint(self.hosts_root, cp)

            try:
                artifacts = self._run_stage(stage, target, target_path, cp)
                record_stage_complete(cp, stage, artifacts=artifacts)
                save_checkpoint(self.hosts_root, cp)
                logger.info("Stage {} completed for {}", stage, target)
            except Exception as e:
                error_msg = f"{type(e).__name__}: {e}"
                record_stage_failure(cp, stage, error_msg)
                save_checkpoint(self.hosts_root, cp)
                logger.error("Stage {} failed for {}: {}", stage, target, error_msg)
                break

        return cp

    def resume(self, target: str) -> Checkpoint | None:
        """Resume pipeline from last checkpoint."""
        cp = load_checkpoint(self.hosts_root, target)
        if cp is None:
            return None

        # Clear previous error so we can retry
        if cp.error:
            cp.error = ""

        return self.digest(target, source_url=cp.source_url)

    def reabsorb(self, target: str) -> Checkpoint | None:
        """Re-run only ABSORB for an already-validated host."""
        cp = load_checkpoint(self.hosts_root, target)
        if cp is None:
            return None

        validation_done = (
            "EXTRACT" in cp.completed_stages
            or "VALIDATE" in cp.completed_stages
        )
        if not validation_done:
            cp.error = "Cannot re-absorb: validation stage not completed"
            return cp

        if "SWALLOW" not in cp.stage_results and "ANALYZE" in cp.stage_results:
            cp.stage_results["SWALLOW"] = cp.stage_results["ANALYZE"]
        if "EXTRACT" not in cp.stage_results and "VALIDATE" in cp.stage_results:
            cp.stage_results["EXTRACT"] = cp.stage_results["VALIDATE"]

        try:
            record_stage_start(cp, "ABSORB")
            artifacts = self._stage_absorb(target, self.hosts_root / target, cp)
            record_stage_complete(cp, "ABSORB", artifacts=artifacts)
            cp.error = ""
            save_checkpoint(self.hosts_root, cp)
        except Exception as error:
            error_msg = f"{type(error).__name__}: {error}"
            record_stage_failure(cp, "ABSORB", error_msg)
            save_checkpoint(self.hosts_root, cp)

        return cp

    # ── Stage implementations ─────────────────────────────────────────

    def _run_stage(
        self,
        stage: str,
        target: str,
        target_path: Path,
        cp: Checkpoint,
    ) -> dict[str, Any]:
        """Dispatch to the correct stage handler."""
        handlers = {
            "ENGULF": self._stage_engulf,
            "ISOLATE": self._stage_isolate,
            "CHEW": self._stage_chew,
            "SWALLOW": self._stage_swallow,
            "DIGEST": self._stage_digest,
            "EXTRACT": self._stage_extract,
            "ABSORB": self._stage_absorb,
        }
        handler = handlers.get(stage)
        if handler is None:
            raise ValueError(f"Unknown stage: {stage}")
        return handler(target, target_path, cp)

    def _stage_engulf(
        self,
        target: str,
        target_path: Path,
        cp: Checkpoint,
    ) -> dict[str, Any]:
        """Stage 1: Identify the target and record metadata."""
        exists = target_path.is_dir()
        file_count = sum(1 for _ in target_path.rglob("*")) if exists else 0

        return {
            "target": target,
            "local_path": str(target_path),
            "exists": exists,
            "file_count": file_count,
            "source_url": cp.source_url,
        }

    def _stage_isolate(
        self,
        target: str,
        target_path: Path,
        cp: Checkpoint,
    ) -> dict[str, Any]:
        """Stage 2: Quick trust check — license, README presence, risk scan."""
        has_readme = any(
            (target_path / name).is_file()
            for name in ("README.md", "readme.md", "README.rst")
        )
        has_license = any(
            (target_path / name).is_file()
            for name in ("LICENSE", "LICENSE.md", "LICENSE.txt", "LICENCE")
        )

        # Try GitHub API for stars (if token available)
        stars = None
        github_token = os.environ.get("GITHUB_TOKEN", "")
        source_url = cp.source_url
        if source_url and "github.com" in source_url and github_token:
            stars = self._fetch_github_stars(source_url, github_token)

        # Compute trust score
        trust = "MEDIUM"
        if has_license and has_readme:
            trust = "HIGH"
        if stars is not None and stars > 1000:
            trust = "VERIFIED"
        if not has_license and not has_readme:
            trust = "LOW"

        cp.trust_score = trust

        return {
            "has_readme": has_readme,
            "has_license": has_license,
            "stars": stars,
            "trust_score": trust,
        }

    def _stage_chew(
        self,
        target: str,
        target_path: Path,
        cp: Checkpoint,
    ) -> dict[str, Any]:
        """Stage 3: Confirm target is isolated in Hosts/."""
        if not target_path.is_dir():
            raise FileNotFoundError(
                f"Target {target} not found in Hosts/. "
                f"Clone it first: git clone <url> {target_path}"
            )

        return {
            "isolated_at": str(target_path),
            "status": "already_isolated",
        }

    def _stage_swallow(
        self,
        target: str,
        target_path: Path,
        cp: Checkpoint,
    ) -> dict[str, Any]:
        """Stage 4: Deep analysis — README, deps, capabilities, risk."""
        analysis = analyze_target(target_path)

        # Generate DIGEST.md
        digest_path = target_path / ".parasite" / "DIGEST.md"
        generate_digest(analysis, digest_path)

        # Special handling for repos with data_catalog capability
        has_data_catalog = any(
            cap.get("kind") == "data_catalog"
            for cap in analysis.get("capabilities", [])
        )
        if has_data_catalog:
            api_entries = analyze_public_apis_readme(target_path)
            if api_entries:
                catalog_path = target_path / ".parasite" / "verified_catalog.json"
                catalog_path.write_text(
                    json.dumps({"entries": api_entries, "count": len(api_entries)}, indent=2),
                    encoding="utf-8",
                )
                analysis["api_entries_parsed"] = len(api_entries)
                analysis["catalog_path"] = str(catalog_path)

        return analysis

    def _stage_digest(
        self,
        target: str,
        target_path: Path,
        cp: Checkpoint,
    ) -> dict[str, Any]:
        """Stage 5: Generate integration artifacts.

        For data repos like public-apis, this means copying the verified
        catalog to ARADHYA's data directory.  For code repos, this would
        generate tool wrappers or skill files.
        """
        integration_plan: list[str] = []

        # Check if we have a verified catalog from the SWALLOW stage
        verified_catalog = target_path / ".parasite" / "verified_catalog.json"
        if verified_catalog.is_file():
            integration_plan.append(f"data_catalog:{verified_catalog}")

        # Check for MCP in analysis
        analyze_result = cp.stage_results.get("SWALLOW", {})
        artifacts = analyze_result.get("artifacts", {})
        if artifacts.get("mcp_detected"):
            integration_plan.append("mcp_server:detected")

        return {
            "integration_plan": integration_plan,
            "artifacts_to_move": len(integration_plan),
        }

    def _stage_extract(
        self,
        target: str,
        target_path: Path,
        cp: Checkpoint,
    ) -> dict[str, Any]:
        """Stage 6: Quality gate — validate generated artifacts."""
        issues: list[str] = []

        # Validate catalog if present
        verified_catalog = target_path / ".parasite" / "verified_catalog.json"
        if verified_catalog.is_file():
            try:
                data = json.loads(verified_catalog.read_text(encoding="utf-8"))
                entries = data.get("entries", [])
                if not entries:
                    issues.append("Catalog has zero entries after validation")

                # Check for garbage entries
                garbage = [
                    e for e in entries
                    if e.get("API", "").startswith(":")
                    or e.get("API", "").startswith("-")
                    or len(e.get("API", "")) < 2
                ]
                if garbage:
                    issues.append(f"Found {len(garbage)} garbage entries in catalog")

            except (json.JSONDecodeError, OSError) as e:
                issues.append(f"Catalog JSON invalid: {e}")

        # Check DIGEST.md exists
        digest = target_path / ".parasite" / "DIGEST.md"
        if not digest.is_file():
            issues.append("DIGEST.md not generated")

        passed = len(issues) == 0
        return {
            "passed": passed,
            "issues": issues,
            "gate": "quality",
        }

    def _stage_absorb(
        self,
        target: str,
        target_path: Path,
        cp: Checkpoint,
    ) -> dict[str, Any]:
        """Stage 7: Move validated artifacts into ARADHYA's live tree."""
        absorbed: list[str] = []

        # Check validation passed
        validate_result = cp.stage_results.get("EXTRACT", {})
        validate_artifacts = validate_result.get("artifacts", {})
        if not validate_artifacts.get("passed", False):
            issues = validate_artifacts.get("issues", [])
            raise RuntimeError(
                f"Cannot absorb — validation failed: {issues}"
            )

        # Copy verified catalog to ARADHYA's data directory
        verified_catalog = target_path / ".parasite" / "verified_catalog.json"
        if verified_catalog.is_file():
            dest = self.project_root / "data" / "processed" / "context" / "public_apis_catalog.json"
            dest.parent.mkdir(parents=True, exist_ok=True)
            data = verified_catalog.read_text(encoding="utf-8")
            dest.write_text(data, encoding="utf-8")
            absorbed.append(f"catalog → {dest}")
            logger.info("Absorbed verified catalog to {}", dest)

        analyze_result = cp.stage_results.get("SWALLOW", {})
        analysis = analyze_result.get("artifacts", {})
        capabilities = [
            str(cap.get("kind", ""))
            for cap in (analysis.get("capabilities", []) or [])
            if isinstance(cap, dict) and cap.get("kind")
        ]
        skill_worthy = {
            "agent_framework",
            "mcp_server",
            "cli_tool",
            "web_scraper",
            "api_client",
        }
        if any(cap in skill_worthy for cap in capabilities):
            try:
                generated = self._generate_skill_file(
                    target,
                    target_path,
                    capabilities,
                    analysis,
                )
                for path in generated:
                    absorbed.append(f"skill -> {path}")
            except Exception as error:
                logger.warning("Skill generation failed for {}: {}", target, error)

        return {
            "absorbed": absorbed,
            "count": len(absorbed),
        }

    # ── Helpers ─────────────────────────────────────────────────────────

    def gc(
        self,
        *,
        strip_git: bool = True,
        archive_completed: bool = False,
        delete_completed: bool = False,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """Plan or run cleanup for digested host repositories.

        Dry-run is the default. Callers should pass ``dry_run=False`` only
        after an explicit confirmation gate has approved the operation.
        """
        results: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        freed_bytes = 0

        if not self.hosts_root.is_dir():
            return self._gc_summary(results, errors, freed_bytes, dry_run)

        for child in sorted(self.hosts_root.iterdir()):
            if not child.is_dir() or child.name.startswith("."):
                continue

            cp = load_checkpoint(self.hosts_root, child.name)
            completed = cp is not None and len(cp.completed_stages) >= 7

            git_dir = child / ".git"
            if strip_git and git_dir.is_dir():
                size = self._directory_size(git_dir)
                result = {
                    "target": child.name,
                    "action": "strip_git",
                    "path": str(git_dir),
                    "freed_bytes": size,
                    "freed_mb": f"{size / (1024 * 1024):.1f}",
                    "dry_run": dry_run,
                    "status": "planned" if dry_run else "done",
                }
                if not dry_run:
                    try:
                        shutil.rmtree(git_dir)
                        self._audit_gc_action(result)
                    except Exception as error:
                        result["status"] = "failed"
                        result["error"] = str(error)
                        errors.append({
                            "target": child.name,
                            "action": "strip_git",
                            "error": str(error),
                        })
                        logger.warning("Failed to strip .git from {}: {}", child.name, error)
                freed_bytes += size
                results.append(result)

            if not completed:
                continue

            if archive_completed and not delete_completed:
                dest = self._archive_destination(child.name)
                result = {
                    "target": child.name,
                    "action": "archive",
                    "path": str(child),
                    "dest": str(dest),
                    "freed_bytes": 0,
                    "freed_mb": "0.0",
                    "dry_run": dry_run,
                    "status": "planned" if dry_run else "done",
                }
                if not dry_run:
                    try:
                        self._archive_completed_host(child, dest)
                        self._audit_gc_action(result)
                    except Exception as error:
                        result["status"] = "failed"
                        result["error"] = str(error)
                        errors.append({
                            "target": child.name,
                            "action": "archive",
                            "error": str(error),
                        })
                        logger.warning("Failed to archive {}: {}", child.name, error)
                results.append(result)

            elif delete_completed:
                size = self._directory_size(child)
                dest = self._archive_destination(child.name)
                result = {
                    "target": child.name,
                    "action": "delete",
                    "path": str(child),
                    "checkpoint_archive": str(dest / ".parasite"),
                    "freed_bytes": size,
                    "freed_mb": f"{size / (1024 * 1024):.1f}",
                    "dry_run": dry_run,
                    "status": "planned" if dry_run else "done",
                }
                if not dry_run:
                    try:
                        self._delete_completed_host(child, dest)
                        self._audit_gc_action(result)
                    except Exception as error:
                        result["status"] = "failed"
                        result["error"] = str(error)
                        errors.append({
                            "target": child.name,
                            "action": "delete",
                            "error": str(error),
                        })
                        logger.warning("Failed to delete {}: {}", child.name, error)
                freed_bytes += size
                results.append(result)

        return self._gc_summary(results, errors, freed_bytes, dry_run)

    def _generate_skill_file(
        self,
        target: str,
        target_path: Path,
        capabilities: list[str],
        analysis: dict[str, Any],
    ) -> list[str]:
        """Generate a validated SKILL.md file for a digested host."""
        slug = self._skill_slug(target)
        skill_name = f"host-{slug}"
        skill_dir = self.project_root / "core" / "skills" / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)

        description = self._clean_skill_text(
            analysis.get("description"),
            fallback=f"Patterns extracted from {target}",
            limit=200,
        )
        project_type = self._clean_skill_text(
            analysis.get("type"),
            fallback="unknown",
            limit=80,
        )
        dependencies = [
            self._clean_skill_text(dep, fallback="", limit=80)
            for dep in analysis.get("dependencies", [])[:15]
        ]
        dependencies = [dep for dep in dependencies if dep]
        clean_capabilities = self._unique_clean(capabilities)
        intents = self._skill_intents(target, clean_capabilities)

        content = self._render_skill_content(
            skill_name=skill_name,
            target=target,
            description=description,
            project_type=project_type,
            capabilities=clean_capabilities,
            dependencies=dependencies,
            intents=intents,
        )
        self._validate_skill_content(content)

        skill_path = skill_dir / "SKILL.md"
        skill_path.write_text(content, encoding="utf-8")
        logger.info("Generated skill file: {}", skill_path)
        return [str(skill_path)]

    @staticmethod
    def _directory_size(path: Path) -> int:
        return sum(
            child.stat().st_size
            for child in path.rglob("*")
            if child.is_file()
        )

    def _archive_destination(self, target_name: str) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return self.hosts_root / ".archived" / f"{target_name}-{timestamp}"

    def _archive_completed_host(self, target_path: Path, dest: Path) -> None:
        parasite_dir = target_path / ".parasite"
        dest.mkdir(parents=True, exist_ok=True)
        if parasite_dir.is_dir():
            shutil.copytree(parasite_dir, dest / ".parasite", dirs_exist_ok=True)
        shutil.rmtree(target_path)

    def _delete_completed_host(self, target_path: Path, dest: Path) -> None:
        parasite_dir = target_path / ".parasite"
        if parasite_dir.is_dir():
            archive_cp = dest / ".parasite"
            archive_cp.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(parasite_dir, archive_cp, dirs_exist_ok=True)
        shutil.rmtree(target_path)

    @staticmethod
    def _gc_summary(
        results: list[dict[str, Any]],
        errors: list[dict[str, str]],
        freed_bytes: int,
        dry_run: bool,
    ) -> dict[str, Any]:
        completed = [result for result in results if result.get("status") == "done"]
        return {
            "dry_run": dry_run,
            "results": results,
            "errors": errors,
            "freed_bytes": freed_bytes,
            "freed_mb": f"{freed_bytes / (1024 * 1024):.1f}",
            "actions_planned": len(results),
            "actions_taken": len(completed),
        }

    @staticmethod
    def _audit_gc_action(result: dict[str, Any]) -> None:
        from src.aradhya.audit_logger import get_audit_logger

        get_audit_logger().log_event(
            "parasite_gc_action",
            {
                "target": result.get("target"),
                "action": result.get("action"),
                "path": result.get("path"),
                "dest": result.get("dest") or result.get("checkpoint_archive", ""),
                "freed_bytes": result.get("freed_bytes", 0),
            },
        )

    @staticmethod
    def _skill_slug(target: str) -> str:
        slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", target.strip()).strip(".-")
        return slug.lower() or "unknown"

    @staticmethod
    def _clean_skill_text(value: Any, *, fallback: str, limit: int) -> str:
        text = str(value or fallback)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", text)
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        text = re.sub(r"[\r\n\t]+", " ", text)
        text = text.replace('"', "").replace("'", "")
        text = re.sub(r"\s+", " ", text).strip()
        return (text or fallback)[:limit]

    @classmethod
    def _unique_clean(cls, values: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for value in values:
            cleaned = cls._clean_skill_text(value, fallback="", limit=80)
            key = cleaned.lower()
            if cleaned and key not in seen:
                seen.add(key)
                out.append(cleaned)
        return out

    @classmethod
    def _skill_intents(cls, target: str, capabilities: list[str]) -> list[str]:
        intents: list[str] = []
        if "agent_framework" in capabilities:
            intents.extend([
                "agent design pattern",
                "orchestration workflow",
                f"how does {target} work",
            ])
        if "mcp_server" in capabilities:
            intents.extend(["MCP server pattern", "tool registration"])
        if "cli_tool" in capabilities:
            intents.extend(["CLI design pattern", "command structure"])
        if "web_scraper" in capabilities:
            intents.extend(["web scraping workflow", "data extraction"])
        if "api_client" in capabilities:
            intents.extend(["API integration", "HTTP client pattern"])
        if not intents:
            intents.append(f"reference material from {target}")
        return cls._unique_clean(intents)

    @staticmethod
    def _render_skill_content(
        *,
        skill_name: str,
        target: str,
        description: str,
        project_type: str,
        capabilities: list[str],
        dependencies: list[str],
        intents: list[str],
    ) -> str:
        intent_lines = "\n".join(f"  - {intent}" for intent in intents)
        capability_lines = (
            "\n".join(f"- **{capability}**" for capability in capabilities)
            if capabilities
            else "- Reference material only"
        )
        dependency_line = (
            ", ".join(f"`{dep}`" for dep in dependencies)
            if dependencies
            else "None detected"
        )
        return (
            "---\n"
            f"name: {skill_name}\n"
            f"description: {description}\n"
            "intents:\n"
            f"{intent_lines}\n"
            "---\n\n"
            f"# Host Digest: {target}\n\n"
            "> Auto-generated skill from Parasite OS digestion pipeline.\n"
            f"> Source: `Hosts/{target}/`\n"
            f"> Type: {project_type}\n\n"
            "## Capabilities Detected\n\n"
            f"{capability_lines}\n\n"
            "## Key Dependencies\n\n"
            f"{dependency_line}\n\n"
            "## Architecture Notes\n\n"
            "This host was analyzed by the 7-stage digestion pipeline.\n"
            f"Refer to `Hosts/{target}/.parasite/DIGEST.md` for the full analysis.\n\n"
            "## Usage Context\n\n"
            "Use this as reference material only. Do not execute code from this host directly.\n"
        )

    @staticmethod
    def _validate_skill_content(content: str) -> None:
        from src.aradhya.skills.skill_loader import _split_frontmatter

        frontmatter, body = _split_frontmatter(content)
        if not body.strip():
            raise ValueError("Generated skill is missing instructions")
        if not frontmatter.get("name"):
            raise ValueError("Generated skill is missing name")
        if not frontmatter.get("description"):
            raise ValueError("Generated skill is missing description")
        intents = frontmatter.get("intents", [])
        if not isinstance(intents, list) or not intents:
            raise ValueError("Generated skill is missing intents")

    def _fetch_github_stars(self, url: str, token: str) -> int | None:
        """Fetch star count from GitHub API."""
        import re
        match = re.search(r"github\.com/([^/]+)/([^/.]+)", url)
        if not match:
            return None

        owner, repo = match.group(1), match.group(2)

        try:
            import requests
            headers = {"Authorization": f"token {token}"}
            resp = requests.get(
                f"https://api.github.com/repos/{owner}/{repo}",
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json().get("stargazers_count")
        except Exception as e:
            logger.warning("GitHub API call failed: {}", e)
            return None
