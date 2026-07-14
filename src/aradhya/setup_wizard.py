"""Interactive first-run setup wizard for Aradhya.

Run with:  python -m src.aradhya.setup_wizard

Inspired by Career-Ops' guided onboarding.  Instead of forcing users
to edit JSON files manually, this walks them through configuration
step-by-step with friendly prompts and auto-detection.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from src.aradhya.paths import get_project_root
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from src.aradhya.utils.helpers import load_json_file

console = Console()

PROJECT_ROOT = get_project_root()
_CONFIG_DIR = PROJECT_ROOT / "core" / "config"
_LEGACY_DIR = PROJECT_ROOT / "core" / "memory"
PROFILE_PATH = _CONFIG_DIR / "profile.json" if _CONFIG_DIR.exists() else _LEGACY_DIR / "profile.json"
# Secrets (cloud API keys) go here — profile.local.json is gitignored, so keys
# never land in the committed profile.json. Deep-merged over profile.json at load.
PROFILE_LOCAL_PATH = _CONFIG_DIR / "profile.local.json" if _CONFIG_DIR.exists() else _LEGACY_DIR / "profile.local.json"
PREFERENCES_PATH = _CONFIG_DIR / "preferences.json" if _CONFIG_DIR.exists() else _LEGACY_DIR / "preferences.json"
USER_RULES_PATH = PROJECT_ROOT / "core" / "memory" / "user_context" / "rules.md"
USER_NOTES_PATH = PROJECT_ROOT / "core" / "memory" / "user_context" / "notes.md"


def _load_json(path: Path) -> dict:
    return load_json_file(path, default={})


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _prompt(question: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    answer = console.input(f"  [bold cyan]?[/] {question}{suffix}: ").strip()
    return answer or default


def _confirm(question: str, default: bool = True) -> bool:
    hint = "[Y/n]" if default else "[y/N]"
    answer = console.input(f"  [bold cyan]?[/] {question} {hint}: ").strip().lower()
    if not answer:
        return default
    return answer in ("y", "yes")


def _detect_ollama_models() -> list[str]:
    """Try to list locally available Ollama models."""
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            models = []
            for line in lines[1:]:  # skip header
                parts = line.split()
                if parts:
                    models.append(parts[0])
            return models
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return []


def _detect_ollama_running() -> bool:
    """Check if Ollama API is reachable."""
    try:
        import requests
        resp = requests.get("http://127.0.0.1:11434/api/tags", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


def step_welcome() -> None:
    console.print()
    console.print(Panel(
        "[bold #00d4aa]Welcome to Aradhya Setup![/]\n\n"
        "I'll walk you through configuring your personal AI assistant.\n"
        "This takes about 2 minutes. You can re-run this anytime with:\n\n"
        "  [dim]python -m src.aradhya.setup_wizard[/]",
        border_style="#00d4aa",
        padding=(1, 4),
    ))
    console.print()


def step_model(profile: dict) -> dict:
    """Configure the AI model provider and model."""
    console.print("[heading]Step 1: AI Model[/]")
    console.print()

    ollama_running = _detect_ollama_running()
    if ollama_running:
        console.print("  [success]✓[/] Ollama is running!")
        models = _detect_ollama_models()
        if models:
            console.print(f"  [dim]Found {len(models)} model(s):[/]")
            table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
            table.add_column("#", style="accent", width=4)
            table.add_column("Model", style="accent")
            for i, m in enumerate(models, 1):
                table.add_row(str(i), m)
            console.print(table)

            current = profile.get("model", {}).get("model_name", "")
            choice = _prompt(
                "Which model to use? (number or name)",
                default=current if current in models else (models[0] if models else ""),
            )
            # Allow number selection
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(models):
                    choice = models[idx]
            except ValueError:
                pass
            profile.setdefault("model", {})["model_name"] = choice
        else:
            console.print("  [warning]⚠[/] No models found. Pull one with: [dim]ollama pull gemma4:e4b[/]")
            model_name = _prompt("Model name to use", default="gemma4:e4b")
            profile.setdefault("model", {})["model_name"] = model_name
    else:
        console.print("  [warning]⚠[/] Ollama is not running.")
        console.print("  [dim]Install from https://ollama.com and run: ollama serve[/]")
        if _confirm("Continue setup without Ollama?"):
            profile.setdefault("model", {})["model_name"] = "gemma4:e4b"
        else:
            console.print("  [dim]Start Ollama and re-run setup.[/]")
            sys.exit(0)

    # Base URL
    base_url = _prompt(
        "Ollama API URL (Press ENTER if running locally)",
        default=profile.get("model", {}).get("base_url", "http://127.0.0.1:11434"),
    )
    profile["model"]["base_url"] = base_url
    profile["model"].setdefault("provider", "ollama")
    profile["model"].setdefault("request_timeout_seconds", 300)
    profile["model"].setdefault(
        "system_prompt",
        "You are Aradhya, a local system assistant focused on safe planning, "
        "clear reasoning, and practical Windows workflow help.",
    )

    # Optional: API keys for cloud models.
    # SECURITY: keys are written ONLY to the gitignored profile.local.json, never
    # to the committed profile.json — so a cloud key can't leak via version control.
    console.print()
    if _confirm("Do you have API keys for cloud models (OpenAI, Anthropic, etc.)?", default=False):
        api_key = _prompt("API key (stored in profile.local.json — gitignored, never committed)")
        api_provider = _prompt("Provider name (openai / anthropic / custom)", default="openai")
        local_profile = _load_json(PROFILE_LOCAL_PATH)
        local_profile.setdefault("model", {})
        local_profile["model"]["cloud_api_key"] = api_key
        local_profile["model"]["cloud_provider"] = api_provider
        _save_json(PROFILE_LOCAL_PATH, local_profile)
        console.print(
            "  [success]✓[/] Cloud key saved to profile.local.json (gitignored). "
            "Aradhya defaults to Ollama and falls back to cloud."
        )

    console.print()
    return profile


def step_voice(profile: dict) -> dict:
    """Configure voice features."""
    console.print("[heading]Step 2: Voice[/]")
    console.print()

    enable_voice = _confirm("Enable voice features (microphone, transcription)?", default=False)

    if enable_voice:
        console.print("  [dim]Voice providers: manual_transcript (default), faster_whisper, whisper_command[/]")
        provider = _prompt("Voice provider", default="faster_whisper")
        profile.setdefault("voice", {})["provider"] = provider

        if provider == "faster_whisper":
            console.print("  [dim]Install voice dependencies: pip install -r requirements-voice.txt[/]")
            model_size = _prompt("Whisper model size (tiny/base/small/medium/large)", default="base")
            profile["voice"]["faster_whisper_model_size"] = model_size

            device = _prompt("Compute device (cpu/cuda)", default="cpu")
            profile["voice"]["faster_whisper_device"] = device

        profile.setdefault("voice_activation", {})["enabled_on_startup"] = _confirm(
            "Auto-start voice listening on launch?", default=False,
        )
    else:
        profile.setdefault("voice", {})["provider"] = "manual_transcript"
        profile.setdefault("voice_activation", {})["enabled_on_startup"] = False

    console.print()
    return profile


def step_user_context() -> None:
    """Set up user context files for personalization."""
    console.print("[heading]Step 3: About You[/]")
    console.print()

    if USER_NOTES_PATH.is_file():
        existing_notes = USER_NOTES_PATH.read_text(encoding="utf-8").strip()
        console.print(Panel(existing_notes, title="Current Profile", border_style="dim"))
        if not _confirm("Do you want to overwrite this profile?", default=False):
            console.print("  [success]✓[/] Kept existing user context.")
            console.print()
            return

    name = _prompt("Your name (Aradhya will remember you)", default="")
    if name:
        USER_NOTES_PATH.parent.mkdir(parents=True, exist_ok=True)
        notes = f"# About the User\n\n- Name: {name}\n"

        role = _prompt("What do you do? (e.g., student, developer, designer)", default="")
        if role:
            notes += f"- Role: {role}\n"

        focus = _prompt("What will you use Aradhya for? (e.g., coding, system tasks, learning)", default="")
        if focus:
            notes += f"- Primary use: {focus}\n"

        USER_NOTES_PATH.write_text(notes, encoding="utf-8")
        console.print("  [success]✓[/] Saved your info to user context.")

    # Rules file
    if not USER_RULES_PATH.is_file():
        USER_RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
        USER_RULES_PATH.write_text(
            "# User Rules\n\n"
            "<!-- Add any rules or preferences for Aradhya here -->\n"
            "<!-- Example: Always use PowerShell, never cmd.exe -->\n",
            encoding="utf-8",
        )

    console.print()


def step_execution(preferences: dict) -> dict:
    """Configure execution safety."""
    console.print("[heading]Step 4: Safety[/]")
    console.print()

    console.print(
        "  Aradhya can execute system commands (open files, run scripts,\n"
        "  manage power). By default, it runs in [bold cyan]careful mode[/]\n"
        "  — read-only commands run instantly, but state-changing actions require confirmation.\n"
    )

    allow = _confirm("Enable careful mode? (No means dry-run only)", default=True)
    preferences["execution_policy"] = "careful" if allow else "dry_run"

    if allow:
        console.print("  [success]✓[/] Careful mode enabled. Aradhya will ask for confirmation before risky actions.")
    else:
        console.print("  [dim]Dry-run mode active. Aradhya will only plan, never execute.[/]")

    console.print()
    return preferences


def step_finish(profile: dict, preferences: dict) -> None:
    """Save everything and show summary."""
    _save_json(PROFILE_PATH, profile)
    _save_json(PREFERENCES_PATH, preferences)

    console.print(Panel(
        "[bold #00d4aa]Setup Complete![/]\n\n"
        f"  🧠 Model: [highlight]{profile.get('model', {}).get('model_name', '?')}[/]\n"
        f"  🎤 Voice: [highlight]{profile.get('voice', {}).get('provider', 'manual_transcript')}[/]\n"
        f"  🔒 Execution: [highlight]{preferences.get('execution_policy', 'careful')}[/]\n\n"
        "Start Aradhya with:\n\n"
        "  [dim]python -m src.aradhya.main[/]\n\n"
        "Type [accent]/help[/accent] to see all commands,\n"
        "or just type naturally — Aradhya understands plain English.",
        border_style="#00d4aa",
        padding=(1, 4),
    ))
    console.print()


def run_wizard() -> None:
    """Run the full interactive setup wizard."""
    step_welcome()

    profile = _load_json(PROFILE_PATH)
    preferences = _load_json(PREFERENCES_PATH)

    profile = step_model(profile)
    profile = step_voice(profile)
    step_user_context()
    preferences = step_execution(preferences)
    step_finish(profile, preferences)


def main() -> None:
    run_wizard()


if __name__ == "__main__":
    main()
