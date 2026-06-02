"""SWALLOW stage — extract capabilities from a Hosts/<target> repo.

This stage reads the target repo's structure and produces a DIGEST.md
summarizing what can be extracted and integrated into ARADHYA.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from loguru import logger

from src.aradhya.cloud_safety import CloudPrivacyGate

# Files to read for understanding a repo
PRIORITY_FILES = (
    "README.md",
    "readme.md",
    "README.rst",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "package.json",
    "requirements.txt",
    "Cargo.toml",
    "go.mod",
)

# Patterns that indicate a repo contains MCP tools
MCP_INDICATORS = (
    "mcp",
    "model-context-protocol",
    "modelcontextprotocol",
    "tool_call",
    "function_call",
)


def analyze_target(target_path: Path) -> dict[str, Any]:
    """Analyze a Hosts/<target> repo and return structured findings.

    Returns a dict with keys:
        - name: target directory name
        - type: "python" | "node" | "rust" | "go" | "data" | "unknown"
        - description: extracted from README first paragraph
        - structure: directory tree summary
        - dependencies: list of dependency names
        - capabilities: list of detected capability types
        - mcp_detected: bool
        - files_scanned: int
        - risk_findings: list of privacy gate findings
        - readme_summary: first ~500 chars of README
    """
    if not target_path.is_dir():
        return {"error": f"Target path {target_path} is not a directory."}

    name = target_path.name
    logger.info("Analyzing target: {}", name)

    result: dict[str, Any] = {
        "name": name,
        "type": "unknown",
        "description": "",
        "structure": {},
        "dependencies": [],
        "capabilities": [],
        "mcp_detected": False,
        "files_scanned": 0,
        "risk_findings": [],
        "readme_summary": "",
    }

    # 1. Detect project type
    result["type"] = _detect_project_type(target_path)

    # 2. Read README
    readme_text = _read_readme(target_path)
    if readme_text:
        result["readme_summary"] = readme_text[:1000]
        result["description"] = _extract_description(readme_text)

    # 3. Scan directory structure
    result["structure"] = _scan_structure(target_path, max_depth=3)
    result["files_scanned"] = _count_files(target_path)

    # 4. Extract dependencies
    result["dependencies"] = _extract_dependencies(target_path, result["type"])

    # 5. Detect capabilities (MCP, tool definitions, API schemas)
    capabilities, mcp_found = _detect_capabilities(target_path, readme_text)
    result["capabilities"] = capabilities
    result["mcp_detected"] = mcp_found

    # 6. Run privacy check on README content
    gate = CloudPrivacyGate()
    if readme_text:
        assessment = gate.assess_text(readme_text, source=f"analyze:{name}")
        result["risk_findings"] = [
            {"code": f.code, "severity": f.severity, "message": f.message}
            for f in assessment.findings
        ]

    return result


def generate_digest(analysis: dict[str, Any], output_path: Path) -> Path:
    """Write a DIGEST.md from analysis results."""
    name = analysis.get("name", "unknown")
    lines = [
        f"# Digest: {name}",
        "",
        f"**Type**: {analysis.get('type', 'unknown')}",
        f"**Files scanned**: {analysis.get('files_scanned', 0)}",
        f"**MCP detected**: {'Yes' if analysis.get('mcp_detected') else 'No'}",
        "",
        "## Description",
        "",
        analysis.get("description", "No description available."),
        "",
    ]

    # Dependencies
    deps = analysis.get("dependencies", [])
    if deps:
        lines.extend(["## Dependencies", ""])
        for dep in deps[:30]:
            lines.append(f"- `{dep}`")
        if len(deps) > 30:
            lines.append(f"- ... and {len(deps) - 30} more")
        lines.append("")

    # Capabilities
    caps = analysis.get("capabilities", [])
    if caps:
        lines.extend(["## Detected Capabilities", ""])
        for cap in caps:
            lines.append(f"- **{cap['kind']}**: {cap['detail']}")
        lines.append("")

    # Risk findings
    risks = analysis.get("risk_findings", [])
    if risks:
        lines.extend(["## Risk Findings", ""])
        for risk in risks:
            emoji = "🚫" if risk["severity"] == "block" else "⚠️"
            lines.append(f"- {emoji} [{risk['severity']}] {risk['message']}")
        lines.append("")

    # Structure
    structure = analysis.get("structure", {})
    if structure:
        lines.extend(["## Directory Structure", "", "```"])
        _format_tree(structure, lines, prefix="")
        lines.extend(["```", ""])

    digest_text = "\n".join(lines)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(digest_text, encoding="utf-8")
    logger.info("Digest written to {}", output_path)
    return output_path


# ── Data-specific analyzers ────────────────────────────────────────────


def analyze_public_apis_readme(target_path: Path) -> list[dict[str, Any]]:
    """Parse the public-apis README.md into verified API entries.

    This is the proper digestion path — validates each entry instead
    of blindly trusting raw markdown parsing.
    """
    readme = target_path / "README.md"
    if not readme.is_file():
        return []

    text = readme.read_text(encoding="utf-8")
    entries: list[dict[str, Any]] = []
    current_category = "Unknown"
    gate = CloudPrivacyGate()

    for line in text.splitlines():
        # Category headers
        if line.startswith("### "):
            current_category = line[4:].strip()
            continue

        # Table rows (skip headers and separators)
        if not line.startswith("|"):
            continue

        parts = [p.strip() for p in line.split("|")[1:-1]]

        # Skip separator rows (|:---|:---|) and header rows
        if len(parts) < 5:
            continue
        if parts[0].lower() == "api" or parts[0].startswith(":"):
            continue
        if all(c in ":-" for c in parts[0].replace(" ", "")):
            continue

        # Parse [Name](URL) format
        name = parts[0]
        link = ""
        link_match = re.search(r"\[(.*?)\]\((.*?)\)", parts[0])
        if link_match:
            name = link_match.group(1).strip()
            link = link_match.group(2).strip()

        # Validate name isn't garbage
        if not name or len(name) < 2 or name.startswith("---"):
            continue

        # Parse HTTPS field
        https_raw = parts[3].strip().lower()
        https = https_raw in ("yes", "true", "1")

        entry = {
            "API": name,
            "Description": parts[1].strip(),
            "Auth": parts[2].strip() or "Unknown",
            "HTTPS": https,
            "Cors": parts[4].strip() if len(parts) > 4 else "Unknown",
            "Link": link,
            "Category": current_category,
        }

        # Run privacy check on each entry's link
        if link:
            assessment = gate.assess_text(link, source=f"api-link:{name}")
            if not assessment.allowed:
                entry["_risk"] = "blocked"
                continue  # Skip entries with suspicious links

        entries.append(entry)

    logger.info("Parsed {} verified API entries from public-apis", len(entries))
    return entries


# ── Internal helpers ───────────────────────────────────────────────────


def _detect_project_type(path: Path) -> str:
    if (path / "pyproject.toml").exists() or (path / "setup.py").exists():
        return "python"
    if (path / "package.json").exists():
        return "node"
    if (path / "Cargo.toml").exists():
        return "rust"
    if (path / "go.mod").exists():
        return "go"
    # Check if it's a data-only repo (mostly markdown/json, no code)
    code_files = list(path.rglob("*.py")) + list(path.rglob("*.js")) + list(path.rglob("*.rs"))
    md_files = list(path.rglob("*.md"))
    if len(md_files) > len(code_files) and len(code_files) < 5:
        return "data"
    return "unknown"


def _read_readme(path: Path) -> str:
    for name in ("README.md", "readme.md", "README.rst", "README.txt", "README"):
        readme = path / name
        if readme.is_file():
            try:
                return readme.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
    return ""


def _extract_description(readme_text: str) -> str:
    """Extract the first meaningful paragraph from a README."""
    lines = readme_text.splitlines()
    paragraphs: list[str] = []
    current: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current:
                paragraphs.append(" ".join(current))
                current = []
        elif stripped.startswith("#") or stripped.startswith("="):
            if current:
                paragraphs.append(" ".join(current))
                current = []
        else:
            current.append(stripped)

    if current:
        paragraphs.append(" ".join(current))

    # Return first paragraph that's longer than a title
    for para in paragraphs:
        if len(para) > 30 and not para.startswith("|"):
            return para[:500]
    return paragraphs[0][:500] if paragraphs else ""


def _scan_structure(path: Path, max_depth: int = 3) -> dict[str, Any]:
    """Build a nested dict representing directory structure."""
    result: dict[str, Any] = {}
    try:
        for child in sorted(path.iterdir()):
            if child.name.startswith(".") and child.name != ".parasite":
                continue
            if child.name in ("node_modules", "__pycache__", ".git", "venv", ".venv"):
                continue
            if child.is_dir() and max_depth > 0:
                sub = _scan_structure(child, max_depth - 1)
                if sub:
                    result[child.name + "/"] = sub
                else:
                    result[child.name + "/"] = "..."
            elif child.is_file():
                result[child.name] = f"{child.stat().st_size} bytes"
    except PermissionError:
        result["_error"] = "permission denied"
    return result


def _count_files(path: Path) -> int:
    count = 0
    try:
        for _ in path.rglob("*"):
            count += 1
            if count > 10000:
                break
    except (PermissionError, OSError):
        pass
    return count


def _extract_dependencies(path: Path, project_type: str) -> list[str]:
    deps: list[str] = []

    if project_type == "python":
        # requirements.txt
        for req_file in ("requirements.txt", "requirements-dev.txt"):
            req_path = path / req_file
            if req_path.is_file():
                for line in req_path.read_text(encoding="utf-8", errors="replace").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        # Strip version specifiers
                        name = re.split(r"[>=<!\[;]", line)[0].strip()
                        if name:
                            deps.append(name)

        # pyproject.toml [project.dependencies]
        pyproject = path / "pyproject.toml"
        if pyproject.is_file():
            try:
                text = pyproject.read_text(encoding="utf-8")
                # Simple regex extraction — no toml parser required
                in_deps = False
                for line in text.splitlines():
                    if "dependencies" in line and "=" in line:
                        in_deps = True
                        continue
                    if in_deps:
                        if line.strip().startswith("]"):
                            in_deps = False
                            continue
                        match = re.search(r'"([^"]+)"', line)
                        if match:
                            name = re.split(r"[>=<!\[;]", match.group(1))[0].strip()
                            if name:
                                deps.append(name)
            except OSError:
                pass

    elif project_type == "node":
        pkg_json = path / "package.json"
        if pkg_json.is_file():
            try:
                pkg = json.loads(pkg_json.read_text(encoding="utf-8"))
                for section in ("dependencies", "devDependencies"):
                    for name in pkg.get(section) or {}:
                        deps.append(name)
            except (OSError, json.JSONDecodeError):
                pass

    return sorted(set(deps))


def _detect_capabilities(
    target_path: Path,
    readme_text: str,
) -> tuple[list[dict[str, str]], bool]:
    """Detect what a repo can offer ARADHYA."""
    capabilities: list[dict[str, str]] = []
    mcp_found = False

    combined_text = readme_text.lower()

    # Check for MCP
    for indicator in MCP_INDICATORS:
        if indicator in combined_text:
            mcp_found = True
            capabilities.append(
                {
                    "kind": "mcp_server",
                    "detail": f"MCP indicator found: '{indicator}'",
                }
            )
            break

    # Check for CLI tools
    if any(p in combined_text for p in ("argparse", "click", "typer", "cli")):
        capabilities.append(
            {
                "kind": "cli_tool",
                "detail": "CLI framework detected",
            }
        )

    # Check for API client
    if any(p in combined_text for p in ("requests", "httpx", "aiohttp", "fetch", "axios")):
        capabilities.append(
            {
                "kind": "api_client",
                "detail": "HTTP client library detected",
            }
        )

    # Check for web scraping
    if any(
        p in combined_text
        for p in ("beautifulsoup", "scrapy", "selenium", "playwright", "puppeteer")
    ):
        capabilities.append(
            {
                "kind": "web_scraper",
                "detail": "Web scraping library detected",
            }
        )

    # Check for data catalog
    if any(p in combined_text for p in ("public api", "api directory", "api list")):
        capabilities.append(
            {
                "kind": "data_catalog",
                "detail": "API directory / catalog detected",
            }
        )

    # Check for agent framework
    if any(p in combined_text for p in ("agent", "langchain", "autogen", "crew", "swarm")):
        capabilities.append(
            {
                "kind": "agent_framework",
                "detail": "Agent/AI framework detected",
            }
        )

    return capabilities, mcp_found


def _format_tree(
    structure: dict[str, Any],
    lines: list[str],
    prefix: str = "",
) -> None:
    items = list(structure.items())
    for i, (name, value) in enumerate(items):
        is_last = i == len(items) - 1
        connector = "└── " if is_last else "├── "
        lines.append(f"{prefix}{connector}{name}")
        if isinstance(value, dict):
            extension = "    " if is_last else "│   "
            _format_tree(value, lines, prefix + extension)
