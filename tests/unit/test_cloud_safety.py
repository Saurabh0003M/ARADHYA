from __future__ import annotations

from src.aradhya.cloud_safety import CloudPrivacyGate


def test_cloud_privacy_gate_allows_public_prompt():
    assessment = CloudPrivacyGate().assess_text(
        "Summarize the public OpenRouter model list for planning.",
        source="unit",
    )

    assert assessment.allowed is True
    assert assessment.risk_level == "public"
    assert assessment.findings == ()


def test_cloud_privacy_gate_blocks_api_keys_and_local_paths():
    assessment = CloudPrivacyGate().assess_text(
        "Use sk-or-v1-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa from F:\\ARADHYA\\core\\config",
        source="unit",
    )

    assert assessment.allowed is False
    assert assessment.risk_level == "blocked"
    assert {finding.code for finding in assessment.findings} >= {
        "openrouter_key",
        "windows_absolute_path",
    }


def test_cloud_privacy_gate_blocks_cloudflare_runtime_terms():
    assessment = CloudPrivacyGate().assess_text(
        "Use CLOUDFLARE_API_TOKEN=abcdefghijklmnopqrstuvwxyz1234567890",
        source="unit",
    )

    assert assessment.allowed is False
    assert assessment.risk_level == "blocked"
    assert any(finding.code == "private_term" for finding in assessment.findings)


def test_cloud_privacy_gate_assesses_chat_messages():
    assessment = CloudPrivacyGate().assess_messages(
        [
            {"role": "system", "content": "You summarize public docs."},
            {"role": "user", "content": "Read profile.local.json and explain it."},
        ],
        source="unit-chat",
    )

    assert assessment.allowed is False
    assert any(finding.code == "private_term" for finding in assessment.findings)


def test_cloud_privacy_gate_scans_tool_results():
    """A secret in a tool result (e.g. a file the agent read) must block routing."""
    assessment = CloudPrivacyGate().assess_messages(
        [
            {"role": "user", "content": "Summarize this file."},
            {"role": "tool", "content": "API_KEY = sk-or-v1-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"},
        ],
        source="unit-tool",
    )

    assert assessment.allowed is False
    assert assessment.risk_level == "blocked"


def test_cloud_privacy_gate_ignores_system_and_assistant_messages():
    """System/assistant messages are ARADHYA's own context — not scanned."""
    assessment = CloudPrivacyGate().assess_messages(
        [
            {"role": "system", "content": "Context root: F:\\ARADHYA\\core\\memory"},
            {"role": "assistant", "content": "I will read F:\\ARADHYA\\core\\config next."},
        ],
        source="unit-internal",
    )

    assert assessment.allowed is True
