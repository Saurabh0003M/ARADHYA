"""Integration ledger for digested host repositories.

The digestion pipeline answers "what is inside this repo?".  The ledger turns
those checkpoint facts into a ranked queue for second-pass integration work.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

from src.aradhya.parasite.checkpoint import STAGES, Checkpoint


LEDGER_PATH = Path("data") / "processed" / "context" / "host_integration_ledger.json"

CAPABILITY_WEIGHTS = {
    "mcp_server": 15,
    "agent_framework": 12,
    "web_scraper": 10,
    "cli_tool": 8,
    "api_client": 8,
    "data_catalog": 6,
}

TRUST_WEIGHTS = {
    "VERIFIED": 12,
    "HIGH": 8,
    "MEDIUM": 2,
    "LOW": -15,
}


@dataclass(frozen=True)
class HostIntegrationCandidate:
    """One digested repo ranked for possible integration."""

    repo: str
    host_path: str
    archived: bool
    status: str
    priority: str
    score: int
    trust_score: str
    project_type: str
    completed_stage_count: int
    current_stage: str
    error: str
    validate_passed: bool
    absorb_completed: bool
    digest_exists: bool
    files_scanned: int
    dependency_count: int
    capabilities: list[str]
    integration_plan: list[str]
    absorbed_count: int
    absorbed_artifacts: list[str]
    description: str
    benefits: list[str]
    recommended_action: str
    next_gate: str


def build_integration_ledger(project_root: Path) -> list[HostIntegrationCandidate]:
    """Build ranked integration candidates from active and archived hosts."""

    hosts_root = project_root / "Hosts"
    candidates: list[HostIntegrationCandidate] = []
    for host_path, archived in _iter_host_dirs(hosts_root):
        cp = _load_checkpoint_from_host(host_path)
        candidates.append(_candidate_from_checkpoint(host_path, archived, cp))
    return sorted(candidates, key=_sort_key)


def write_integration_ledger(
    project_root: Path,
    candidates: list[HostIntegrationCandidate] | None = None,
) -> Path:
    """Persist the current ledger to data/processed/context."""

    if candidates is None:
        candidates = build_integration_ledger(project_root)

    output_path = project_root / LEDGER_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "source": "Hosts/.parasite/checkpoint.json",
        "candidate_count": len(candidates),
        "candidates": [asdict(candidate) for candidate in candidates],
    }
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return output_path


def find_candidate(
    candidates: list[HostIntegrationCandidate],
    repo: str,
) -> HostIntegrationCandidate | None:
    """Find a candidate by checkpoint repo name or directory name."""

    normalized = repo.strip().lower()
    for candidate in candidates:
        host_name = Path(candidate.host_path).name.lower()
        if candidate.repo.lower() == normalized or host_name == normalized:
            return candidate
    return None


def _iter_host_dirs(hosts_root: Path) -> list[tuple[Path, bool]]:
    if not hosts_root.is_dir():
        return []

    dirs: list[tuple[Path, bool]] = []
    for child in sorted(hosts_root.iterdir(), key=lambda p: p.name.lower()):
        if child.is_dir() and not child.name.startswith("."):
            dirs.append((child, False))

    archived_root = hosts_root / ".archived"
    if archived_root.is_dir():
        for child in sorted(archived_root.iterdir(), key=lambda p: p.name.lower()):
            if child.is_dir():
                dirs.append((child, True))
    return dirs


def _load_checkpoint_from_host(host_path: Path) -> Checkpoint | None:
    path = host_path / ".parasite" / "checkpoint.json"
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    return Checkpoint(
        target=str(raw.get("target", host_path.name)),
        source_url=str(raw.get("source_url", "")),
        current_stage=str(raw.get("current_stage", "ENGULF")),
        completed_stages=list(raw.get("completed_stages", [])),
        stage_results=dict(raw.get("stage_results", {})),
        started_at=str(raw.get("started_at", "")),
        last_checkpoint=str(raw.get("last_checkpoint", "")),
        trust_score=str(raw.get("trust_score", "")),
        error=str(raw.get("error", "")),
    )


def _candidate_from_checkpoint(
    host_path: Path,
    archived: bool,
    cp: Checkpoint | None,
) -> HostIntegrationCandidate:
    digest_exists = (host_path / ".parasite" / "DIGEST.md").is_file()

    if cp is None:
        return HostIntegrationCandidate(
            repo=host_path.name,
            host_path=str(host_path),
            archived=archived,
            status="not_digested",
            priority="blocked",
            score=0,
            trust_score="",
            project_type="unknown",
            completed_stage_count=0,
            current_stage="NOT_STARTED",
            error="missing checkpoint",
            validate_passed=False,
            absorb_completed=False,
            digest_exists=digest_exists,
            files_scanned=0,
            dependency_count=0,
            capabilities=[],
            integration_plan=[],
            absorbed_count=0,
            absorbed_artifacts=[],
            description="",
            benefits=[],
            recommended_action="Run /parasite digest before considering integration.",
            next_gate="Complete the 7-stage digestion pipeline.",
        )

    stage_results = cp.stage_results or {}
    analysis = _artifacts(stage_results, "SWALLOW")
    validate = _artifacts(stage_results, "EXTRACT")
    integrate = _artifacts(stage_results, "DIGEST")
    absorb = _artifacts(stage_results, "ABSORB")
    absorb_result = stage_results.get("ABSORB", {})

    capabilities = _capability_kinds(analysis)
    integration_plan = [
        str(item)
        for item in integrate.get("integration_plan", [])
    ]
    absorbed_artifacts = [
        str(item)
        for item in absorb.get("absorbed", [])
    ]
    absorbed_count = int(absorb.get("count", len(absorbed_artifacts)) or 0)
    validate_passed = validate.get("passed") is True
    absorb_completed = absorb_result.get("status") == "completed"
    completed_stage_count = len(cp.completed_stages)
    is_complete = completed_stage_count == len(STAGES)
    status = _status(cp, is_complete, validate_passed, absorb_completed)
    score = _score_candidate(
        cp=cp,
        is_complete=is_complete,
        validate_passed=validate_passed,
        absorb_completed=absorb_completed,
        digest_exists=digest_exists,
        capabilities=capabilities,
        integration_plan=integration_plan,
        absorbed_count=absorbed_count,
        files_scanned=int(analysis.get("files_scanned", 0) or 0),
        dependency_count=len(analysis.get("dependencies", []) or []),
    )
    priority = _priority(
        cp=cp,
        is_complete=is_complete,
        absorbed_count=absorbed_count,
        score=score,
        files_scanned=int(analysis.get("files_scanned", 0) or 0),
        dependency_count=len(analysis.get("dependencies", []) or []),
    )

    return HostIntegrationCandidate(
        repo=cp.target,
        host_path=str(host_path),
        archived=archived,
        status=status,
        priority=priority,
        score=score,
        trust_score=cp.trust_score,
        project_type=str(analysis.get("type", "unknown")),
        completed_stage_count=completed_stage_count,
        current_stage=cp.current_stage,
        error=cp.error,
        validate_passed=validate_passed,
        absorb_completed=absorb_completed,
        digest_exists=digest_exists,
        files_scanned=int(analysis.get("files_scanned", 0) or 0),
        dependency_count=len(analysis.get("dependencies", []) or []),
        capabilities=capabilities,
        integration_plan=integration_plan,
        absorbed_count=absorbed_count,
        absorbed_artifacts=absorbed_artifacts,
        description=_compact(str(analysis.get("description", "")), limit=240),
        benefits=_benefits(capabilities, absorbed_count),
        recommended_action=_recommended_action(cp.target, capabilities, absorbed_count),
        next_gate=_next_gate(priority, capabilities, absorbed_count),
    )


def _artifacts(stage_results: dict[str, Any], stage: str) -> dict[str, Any]:
    result = stage_results.get(stage, {})
    artifacts = result.get("artifacts", {}) if isinstance(result, dict) else {}
    return artifacts if isinstance(artifacts, dict) else {}


def _capability_kinds(analysis: dict[str, Any]) -> list[str]:
    capabilities: list[str] = []
    for cap in analysis.get("capabilities", []) or []:
        if isinstance(cap, dict):
            kind = str(cap.get("kind", "")).strip()
            if kind and kind not in capabilities:
                capabilities.append(kind)
    return capabilities


def _status(
    cp: Checkpoint,
    is_complete: bool,
    validate_passed: bool,
    absorb_completed: bool,
) -> str:
    if cp.error:
        return "error"
    if is_complete and validate_passed and absorb_completed:
        return "ready"
    if is_complete:
        return "complete_needs_review"
    if cp.completed_stages:
        return "partial"
    return "not_started"


def _score_candidate(
    *,
    cp: Checkpoint,
    is_complete: bool,
    validate_passed: bool,
    absorb_completed: bool,
    digest_exists: bool,
    capabilities: list[str],
    integration_plan: list[str],
    absorbed_count: int,
    files_scanned: int,
    dependency_count: int,
) -> int:
    score = 0
    if is_complete:
        score += 15
    if validate_passed:
        score += 10
    if absorb_completed:
        score += 5
    if digest_exists:
        score += 5
    if cp.error:
        score -= 50

    score += TRUST_WEIGHTS.get(cp.trust_score, 0)
    for capability in capabilities:
        score += CAPABILITY_WEIGHTS.get(capability, 0)
    score += min(16, len(integration_plan) * 4)
    if absorbed_count:
        score += 25

    if files_scanned > 5000:
        score -= 12
    elif files_scanned > 3000:
        score -= 8
    if dependency_count > 100:
        score -= 8
    elif dependency_count > 50:
        score -= 4

    return max(0, min(100, score))


def _priority(
    *,
    cp: Checkpoint,
    is_complete: bool,
    absorbed_count: int,
    score: int,
    files_scanned: int,
    dependency_count: int,
) -> str:
    if cp.error or not is_complete:
        return "blocked"
    if absorbed_count:
        return "live"
    if files_scanned > 3000 or dependency_count > 100:
        return "large-review"
    if score >= 85:
        return "integrate-now"
    if score >= 65:
        return "review-next"
    return "reference"


def _benefits(capabilities: list[str], absorbed_count: int) -> list[str]:
    benefits: list[str] = []
    if absorbed_count:
        benefits.append("Live artifact already available in Aradhya.")
    if "agent_framework" in capabilities:
        benefits.append("Agent roles, orchestration patterns, or worker design.")
    if "mcp_server" in capabilities:
        benefits.append("MCP/tool registration patterns for future wrappers.")
    if "cli_tool" in capabilities:
        benefits.append("CLI command and terminal workflow patterns.")
    if "web_scraper" in capabilities:
        benefits.append("Web research and extraction workflow patterns.")
    if "api_client" in capabilities:
        benefits.append("API integration and request handling patterns.")
    if "data_catalog" in capabilities:
        benefits.append("Structured catalog/reference data candidate.")
    if not benefits:
        benefits.append("Reference material only until a second-pass review finds a reusable artifact.")
    return benefits


def _recommended_action(
    repo: str,
    capabilities: list[str],
    absorbed_count: int,
) -> str:
    if absorbed_count:
        return "Keep live artifact and improve commands that consume it."
    if repo == "agency-agents":
        return "Promote selected agent definitions into local Aradhya skills."
    if repo == "Scrapegraph-ai":
        return "Extract a safe web research/scraping workflow, keeping execution behind confirmation."
    if "mcp_server" in capabilities:
        return "Inspect MCP entry points and design a local wrapper before copying code."
    if "data_catalog" in capabilities:
        return "Validate catalog structure and decide whether it should become a local dataset."
    if "agent_framework" in capabilities:
        return "Extract architecture notes or skill templates, not executable code."
    return "Keep as reference until a concrete integration target is identified."


def _next_gate(
    priority: str,
    capabilities: list[str],
    absorbed_count: int,
) -> str:
    if absorbed_count:
        return "Run user-facing command checks against the live artifact."
    if priority == "blocked":
        return "Fix checkpoint error or resume digestion."
    if priority == "large-review":
        return "Read the digest and select one narrow artifact before touching code."
    if "mcp_server" in capabilities:
        return "Locate server entry point, tool schema, and safety surface."
    if "agent_framework" in capabilities:
        return "Choose one small skill/persona/workflow to promote."
    return "Manual review for a concrete user-facing benefit."


def _sort_key(candidate: HostIntegrationCandidate) -> tuple[int, int, str]:
    priority_rank = {
        "live": 0,
        "integrate-now": 1,
        "review-next": 2,
        "large-review": 3,
        "reference": 4,
        "blocked": 5,
    }.get(candidate.priority, 6)
    return (priority_rank, -candidate.score, candidate.repo.lower())


def _compact(text: str, *, limit: int) -> str:
    compacted = " ".join(text.split())
    if len(compacted) <= limit:
        return compacted
    return compacted[: limit - 3].rstrip() + "..."
