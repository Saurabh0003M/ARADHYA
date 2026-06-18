"""Privacy checks for optional cloud model use.

Aradhya is local-first.  This module is the small gate that prevents obvious
secrets, private files, and local machine details from being sent to optional
cloud model providers such as OpenRouter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CloudSafetyFinding:
    """A single reason a payload needs review or must be blocked."""

    code: str
    severity: str
    message: str
    evidence: str = ""


@dataclass(frozen=True)
class CloudSafetyAssessment:
    """Result of assessing text before cloud model use."""

    allowed: bool
    risk_level: str
    summary: str
    findings: tuple[CloudSafetyFinding, ...] = ()


class CloudPrivacyGate:
    """Detect high-risk payloads before optional cloud routing."""

    _BLOCK_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
        (
            "openrouter_key",
            re.compile(r"\bsk-or-v1-[A-Za-z0-9_-]{20,}\b"),
            "OpenRouter API key-like text detected.",
        ),
        (
            "generic_secret_key",
            re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
            "API key-like text detected.",
        ),
        (
            "aws_access_key",
            re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
            "AWS access key-like text detected.",
        ),
        (
            "private_key_block",
            re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", re.IGNORECASE),
            "Private key material detected.",
        ),
        (
            "named_secret",
            re.compile(
                r"(?i)\b(api[_-]?key|secret|password|token)\b\s*[:=]\s*['\"]?"
                r"[A-Za-z0-9_./+=:-]{8,}"
            ),
            "Named secret assignment detected.",
        ),
    )

    # Windows paths are flagged for review (not blocked) — they leak
    # local directory structure but are not secrets.  Whitelisted prefixes
    # suppress even the review finding.
    _WINDOWS_PATH_PATTERN: tuple[str, re.Pattern[str], str] = (
        "windows_absolute_path",
        re.compile(r"\b[A-Za-z]:\\[^\s\"'<>|]+"),
        "Local Windows path detected.",
    )

    _PRIVATE_TERMS: tuple[str, ...] = (
        ".env",
        "audit.jsonl",
        "core/audit",
        "core\\audit",
        "core/memory",
        "core\\memory",
        "profile.local.json",
        "ARADHYA_OPENROUTER_API_KEY",
        "OPUS_OPENROUTER_API_KEY",
    )

    _REVIEW_TERMS: tuple[str, ...] = (
        "personal",
        "private",
        "credential",
        "medical",
        "financial",
        "bank",
        "address",
    )

    def __init__(
        self,
        *,
        path_whitelist: list[str] | None = None,
    ) -> None:
        # Normalised prefixes that are allowed to appear in cloud payloads.
        # E.g. ["f:\\aradhya", "c:\\users\\saura\\projects"]
        self._path_whitelist = [
            p.lower().replace("/", "\\") for p in (path_whitelist or [])
        ]

    def _is_whitelisted_path(self, path: str) -> bool:
        """Return True if *path* starts with a whitelisted prefix."""
        normalised = path.lower().replace("/", "\\")
        return any(normalised.startswith(prefix) for prefix in self._path_whitelist)

    def assess_text(self, text: str, *, source: str = "manual") -> CloudSafetyAssessment:
        """Return whether text may be sent to an optional cloud model."""

        normalized = text or ""
        findings: list[CloudSafetyFinding] = []

        for code, pattern, message in self._BLOCK_PATTERNS:
            match = pattern.search(normalized)
            if match:
                findings.append(
                    CloudSafetyFinding(
                        code=code,
                        severity="block",
                        message=message,
                        evidence=self._redact(match.group(0)),
                    )
                )

        # Windows paths — review-level, skipped if whitelisted
        code, pattern, message = self._WINDOWS_PATH_PATTERN
        for match in pattern.finditer(normalized):
            if not self._is_whitelisted_path(match.group(0)):
                findings.append(
                    CloudSafetyFinding(
                        code=code,
                        severity="review",
                        message=message,
                        evidence=self._redact(match.group(0)),
                    )
                )
                break  # one finding is enough

        lowered = normalized.lower()
        for term in self._PRIVATE_TERMS:
            if term.lower() in lowered:
                findings.append(
                    CloudSafetyFinding(
                        code="private_term",
                        severity="block",
                        message=f"Private runtime term detected: {term}",
                        evidence=term,
                    )
                )

        if not findings:
            for term in self._REVIEW_TERMS:
                if term in lowered:
                    findings.append(
                        CloudSafetyFinding(
                            code="sensitive_topic",
                            severity="review",
                            message=f"Sensitive topic marker detected: {term}",
                            evidence=term,
                        )
                    )
                    break

        has_block = any(f.severity == "block" for f in findings)
        risk_level = "blocked" if has_block else ("review" if findings else "public")
        if has_block:
            summary = f"Blocked cloud routing for {source}; private or secret-like content was detected."
        elif findings:
            summary = f"Cloud routing is allowed for {source}, but the payload deserves human review."
        else:
            summary = f"Cloud routing is allowed for {source}; no private markers were detected."

        return CloudSafetyAssessment(
            allowed=not has_block,
            risk_level=risk_level,
            summary=summary,
            findings=tuple(findings),
        )

    def assess_messages(
        self,
        messages: list[dict[str, Any]],
        *,
        source: str = "chat messages",
    ) -> CloudSafetyAssessment:
        """Assess OpenAI-style chat messages before optional cloud routing.

        Scans USER messages and TOOL results. System and assistant messages
        are ARADHYA's own context / prior model output and reference internal
        paths that would only cause false positives. Tool results, however, can
        carry data the agent read from disk (e.g. a file containing an API key
        or a command's output), so they are scanned too — otherwise a secret
        read by ``read_file`` could be relayed to a cloud model on the next turn.
        """

        text_parts: list[str] = []
        for message in messages:
            role = str(message.get("role", "message"))
            # Scan what the user typed and what tools returned (file reads,
            # command output). Skip system/assistant — they legitimately
            # reference internal paths like core/memory and would false-positive.
            if role not in ("user", "tool"):
                continue
            content = self._extract_text(message.get("content", ""))
            if content:
                text_parts.append(content)
        return self.assess_text("\n".join(text_parts), source=source)

    def _extract_text(self, value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            return " ".join(self._extract_text(v) for v in value.values())
        if isinstance(value, list):
            return " ".join(self._extract_text(v) for v in value)
        return str(value) if value is not None else ""

    def _redact(self, value: str) -> str:
        if len(value) <= 10:
            return "***"
        return f"{value[:4]}...{value[-4:]}"
