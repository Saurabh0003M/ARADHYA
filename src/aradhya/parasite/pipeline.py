"""Digestion pipeline — the core of Parasite OS.

Orchestrates the 7-stage pipeline:
    DISCOVER → VERIFY → ISOLATE → ANALYZE → INTEGRATE → VALIDATE → ABSORB

Each stage writes a checkpoint so the pipeline can resume after any
termination (crash, high traffic, user Ctrl+C).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from loguru import logger

from src.aradhya.parasite.checkpoint import (
    STAGES,
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
            "DISCOVER": self._stage_discover,
            "VERIFY": self._stage_verify,
            "ISOLATE": self._stage_isolate,
            "ANALYZE": self._stage_analyze,
            "INTEGRATE": self._stage_integrate,
            "VALIDATE": self._stage_validate,
            "ABSORB": self._stage_absorb,
        }
        handler = handlers.get(stage)
        if handler is None:
            raise ValueError(f"Unknown stage: {stage}")
        return handler(target, target_path, cp)

    def _stage_discover(
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

    def _stage_verify(
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

    def _stage_isolate(
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

    def _stage_analyze(
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

        # Special handling for public-apis repo
        if target == "public-apis" and analysis.get("type") == "data":
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

    def _stage_integrate(
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

        # Check if we have a verified catalog from the ANALYZE stage
        verified_catalog = target_path / ".parasite" / "verified_catalog.json"
        if verified_catalog.is_file():
            integration_plan.append(f"data_catalog:{verified_catalog}")

        # Check for MCP in analysis
        analyze_result = cp.stage_results.get("ANALYZE", {})
        artifacts = analyze_result.get("artifacts", {})
        if artifacts.get("mcp_detected"):
            integration_plan.append("mcp_server:detected")

        return {
            "integration_plan": integration_plan,
            "artifacts_to_move": len(integration_plan),
        }

    def _stage_validate(
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
        validate_result = cp.stage_results.get("VALIDATE", {})
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

        return {
            "absorbed": absorbed,
            "count": len(absorbed),
        }

    # ── Helpers ─────────────────────────────────────────────────────────

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
