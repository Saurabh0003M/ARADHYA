"""Stage 0 acceptance — the ten commands, run through the real brain and the
real MCP server, without the microphone.

Why this exists separately from the voice loop: the acceptance bar is
*"open X / click Y / read this window" by voice, 10/10 on 3 apps, monitor off*.
That is two claims bolted together — the tools work, and the microphone works —
and debugging them together is how you end up unable to say which one failed.
So this file drives the identical brain + identical MCP server with the ten
commands as **text**. If it passes, a voice failure is a microphone failure.

The ten commands below are the **permanent regression list**. They are what
Acceptance Run A (Claude SDK brain) and Acceptance Run B (OpenCode over the
freellmapi proxy) both run, so any regression after the brain swap is the
brain's fault by construction. Do not quietly reword them: a changed command is
a changed test.

Run (from `lite/`, in lite's own venv, with the effectors unlocked)::

    $env:ARADHYA_ACCEPT_UNLOCK = "1"
    .venv\\Scripts\\python.exe acceptance.py

Every gated tool is denied unless that variable is set — four of the ten
commands are gated (typing, pressing, opening a browser, navigating), so a
locked run is expected to score 6/10 and say so.
"""

from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass, field

import aradhya_lite
from claude_agent_sdk import AssistantMessage, ClaudeSDKClient, TextBlock


@dataclass(frozen=True)
class Command:
    """One acceptance command and what it has to actually do."""

    index: int
    app: str
    spoken: str
    #: The MCP tool that must appear in the turn. Naming it is the difference
    #: between "the model said it opened Notepad" and "Notepad opened".
    expects_tool: str
    gated: bool = False


#: THE TEN. Three apps, both effector legs, read-only and gated mixed.
COMMANDS: tuple[Command, ...] = (
    # ── Notepad ───────────────────────────────────────────────────────
    Command(1, "desktop", "Which windows are open right now?", "list_windows"),
    Command(2, "Notepad", "Bring Notepad to the front.", "focus_window", gated=True),
    Command(3, "Notepad", "Read the Notepad window and tell me what I can click.",
            "list_window_controls"),
    Command(4, "Notepad", "Type hello from Aradhya into Notepad.",
            "set_control_text", gated=True),
    # ── Calculator ────────────────────────────────────────────────────
    Command(5, "Calculator", "Switch to Calculator.", "focus_window", gated=True),
    Command(6, "Calculator", "Read this window and tell me what buttons it has.",
            "list_window_controls"),
    Command(7, "Calculator", "Press the seven button in Calculator.",
            "invoke_control", gated=True),
    # ── Browser ───────────────────────────────────────────────────────
    Command(8, "Browser", "Open the browser.", "browser_open", gated=True),
    Command(9, "Browser", "Go to example dot com.", "browser_navigate", gated=True),
    Command(10, "Browser", "Read this page and tell me what is on it.", "browser_read"),
)

DENIAL_MARKERS = ("requires confirmation", "was not approved", "not yet ported")


@dataclass
class Outcome:
    command: Command
    tools_used: list[str] = field(default_factory=list)
    reply: str = ""
    denied: bool = False
    error: str = ""

    @property
    def passed(self) -> bool:
        if self.error or self.denied:
            return False
        return any(self.command.expects_tool in tool for tool in self.tools_used)

    @property
    def verdict(self) -> str:
        if self.error:
            return f"ERROR   {self.error[:60]}"
        if self.denied:
            return "DENIED  (gated tool, session not unlocked)"
        if not self.passed:
            used = ", ".join(self.tools_used) or "none"
            return f"NO TOOL expected {self.command.expects_tool}, used: {used}"
        return "pass"


def _blocks(message) -> list:
    return list(getattr(message, "content", []) or [])


async def run_one(client: ClaudeSDKClient, command: Command) -> Outcome:
    outcome = Outcome(command=command)
    try:
        await client.query(command.spoken)
        texts: list[str] = []
        async for message in client.receive_response():
            if not isinstance(message, AssistantMessage):
                continue
            for block in _blocks(message):
                if isinstance(block, TextBlock) and block.text:
                    texts.append(block.text)
                name = getattr(block, "name", None)
                if name:
                    outcome.tools_used.append(str(name))
                content = str(getattr(block, "content", "") or "")
                if any(marker in content for marker in DENIAL_MARKERS):
                    outcome.denied = True
        outcome.reply = " ".join(texts).strip()
    except Exception as error:  # a crashed turn is a failed command, not a crash
        outcome.error = f"{type(error).__name__}: {error}"
    return outcome


async def main() -> int:
    unlocked = os.environ.get("ARADHYA_ACCEPT_UNLOCK", "").strip() in {"1", "true", "yes"}
    aradhya_lite.INTERACTION_UNLOCKED = unlocked

    gated = sum(1 for command in COMMANDS if command.gated)
    print(f"Stage 0 acceptance — {len(COMMANDS)} commands, effectors "
          f"{'UNLOCKED' if unlocked else 'LOCKED'}")
    if not unlocked:
        print(f"  {gated} gated commands will be denied. Set ARADHYA_ACCEPT_UNLOCK=1 "
              f"for the real run.\n")

    outcomes: list[Outcome] = []
    async with ClaudeSDKClient(options=aradhya_lite.build_options()) as client:
        for command in COMMANDS:
            print(f"\n[{command.index:2d}] ({command.app}) {command.spoken}")
            outcome = await run_one(client, command)
            outcomes.append(outcome)
            print(f"     tools: {', '.join(outcome.tools_used) or '(none)'}")
            print(f"     said : {outcome.reply[:150]}")
            print(f"     -> {outcome.verdict}")

    passed = sum(1 for outcome in outcomes if outcome.passed)
    print("\n" + "=" * 66)
    print(f"ACCEPTANCE: {passed}/{len(COMMANDS)}")
    for outcome in outcomes:
        mark = "ok  " if outcome.passed else "FAIL"
        print(f"  {mark} {outcome.command.index:2d}. ({outcome.command.app}) "
              f"{outcome.command.spoken}  — {outcome.verdict}")
    if passed < len(COMMANDS):
        print("\nNot 10/10. Report the failures; do not re-word the commands to "
              "make them pass — they are the regression list.")
    return 0 if passed == len(COMMANDS) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
