"""Floating shell UI for the user-facing Aradhya experience."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import threading
import tkinter as tk
from tkinter import filedialog, scrolledtext
from typing import Callable

from loguru import logger

from src.aradhya.assistant_core import AradhyaAssistant
from src.aradhya.assistant_models import ShellStateSnapshot, WakeSource
from src.aradhya.logging_utils import configure_logging
from src.aradhya.model_provider import build_text_model_provider
from src.aradhya.runtime_profile import RuntimeProfile, load_runtime_profile
from src.aradhya.voice_activation import (
    VoiceActivatedAradhya,
    describe_voice_capture_support,
)
from src.aradhya.voice_pipeline import VoiceInboxManager

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ShellControlSpec:
    """Declarative description of a floating-shell control."""

    control_id: str
    label: str
    tooltip: str


class FloatingShellController:
    """Behavior layer for the floating shell that is independent of Tk widgets."""

    def __init__(
        self,
        assistant: AradhyaAssistant,
        runtime_profile: RuntimeProfile,
        voice_manager: VoiceInboxManager,
        *,
        voice_runtime_factory: Callable[[Callable[[str], None]], VoiceActivatedAradhya] | None = None,
    ) -> None:
        self.assistant = assistant
        self.runtime_profile = runtime_profile
        self.voice_manager = voice_manager
        self.voice_manager.ensure_directories()
        self._screen_attachment_path: Path | None = None
        self._voice_runtime_factory = voice_runtime_factory or self._build_voice_runtime

    def control_specs(self) -> tuple[ShellControlSpec, ...]:
        """Return the controls rendered by the floating shell."""

        return (
            ShellControlSpec(
                "mic",
                "Mic",
                "Start one-tap voice capture when live voice input is configured.",
            ),
            ShellControlSpec(
                "screen",
                "Screen",
                "Bounded screenshot-guidance mode for what is currently on screen.",
            ),
            ShellControlSpec(
                "advanced",
                "A",
                "Higher accuracy for the next request only. Response may take longer.",
            ),
            ShellControlSpec(
                "interaction",
                "I",
                "Interaction locked or unlocked for user-level machine actions in this session.",
            ),
        )

    def shell_state_snapshot(self) -> ShellStateSnapshot:
        """Return the shell-visible state snapshot from the assistant core."""

        return self.assistant.shell_state_snapshot()

    def status_line(self) -> str:
        """Render a compact status line for the floating shell."""

        snapshot = self.shell_state_snapshot()
        interaction_label = "Interaction unlocked" if snapshot.interaction_enabled else "Interaction locked"
        advanced_label = "A armed" if snapshot.advanced_next_request else "A normal"
        screen_label = "Screen on" if snapshot.screen_context_active else "Screen off"
        cloud_label = "Cloud off" if not snapshot.cloud_features_enabled else "Cloud on"
        return (
            f"Local only | Model: {self.runtime_profile.model.model_name} | "
            f"{interaction_label} | {advanced_label} | {screen_label} | {cloud_label}"
        )

    def toggle_interaction(self) -> str:
        """Toggle whether user-level machine interaction is unlocked."""

        enabled = not self.assistant.state.interaction_enabled
        snapshot = self.assistant.set_interaction_enabled(enabled)
        if snapshot.interaction_enabled:
            return "Aradhya > Interaction unlocked for this session. User-level actions can run after confirmation."
        return "Aradhya > Interaction locked. Aradhya can still plan, but not execute user-level machine actions."

    def arm_advanced_request(self) -> str:
        """Enable one-shot advanced reasoning for the next request only."""

        self.assistant.arm_advanced_next_request()
        return "Aradhya > Advanced mode is armed for the next request only."

    def toggle_screen_context(self, screenshot_path: Path | None = None) -> str:
        """Toggle bounded screen-guidance mode and optionally attach a screenshot path."""

        active = not self.assistant.state.screen_context_active
        self.assistant.set_screen_context_active(active)
        if not active:
            self._screen_attachment_path = None
            return "Aradhya > Screen guidance mode is off."

        self._screen_attachment_path = screenshot_path
        if screenshot_path is not None:
            return (
                "Aradhya > Screen guidance mode is active. "
                f"Attached screenshot: {screenshot_path.name}. Describe what you need help with."
            )
        return (
            "Aradhya > Screen guidance mode is active. "
            "Describe what is on screen or pick a screenshot to guide the request."
        )

    def screen_attachment_path(self) -> Path | None:
        """Return the currently attached screenshot, if any."""

        return self._screen_attachment_path

    def submit_text(self, text: str) -> tuple[str, ...]:
        """Route a shell text submission through the existing assistant core."""

        lines: list[str] = []
        normalized_text = " ".join(text.split())
        if not normalized_text:
            return ("Aradhya > Type a request or use Mic.",)

        if not self.assistant.state.is_awake:
            wake_response = self.assistant.handle_wake(WakeSource.FLOATING_ICON)
            lines.append(f"Aradhya > {wake_response.spoken_response}")

        if self.assistant.state.screen_context_active and self._screen_attachment_path is not None:
            lines.append(
                f"Screen > Using attached screenshot reference: {self._screen_attachment_path.name}"
            )

        response = self.assistant.handle_transcript(normalized_text)
        if response.transcript_echo:
            lines.append(f"Heard > {response.transcript_echo}")
        lines.append(f"Aradhya > {response.spoken_response}")
        return tuple(lines)

    def capture_once(self) -> tuple[str, ...]:
        """Run one-tap voice capture and return the surfaced output lines."""

        support = describe_voice_capture_support(self.runtime_profile)
        if not support.available:
            return (f"Voice > {support.message}",)

        lines: list[str] = []
        try:
            runtime = self._voice_runtime_factory(lines.append)
            runtime.capture_once()
        except Exception as error:
            logger.warning("Floating shell mic capture failed: {}", error)
            lines.append(f"Voice > Mic capture failed: {error}")
        return tuple(lines)

    def _build_voice_runtime(self, output_handler: Callable[[str], None]) -> VoiceActivatedAradhya:
        return VoiceActivatedAradhya(
            assistant=self.assistant,
            voice_manager=self.voice_manager,
            runtime_profile=self.runtime_profile,
            output_handler=output_handler,
        )


class _Tooltip:
    """Very small tooltip helper for Tk buttons."""

    def __init__(self, widget: tk.Widget, text: str) -> None:
        self.widget = widget
        self.text = text
        self._window: tk.Toplevel | None = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, _event=None) -> None:
        if self._window is not None or not self.text:
            return

        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        self._window = tk.Toplevel(self.widget)
        self._window.wm_overrideredirect(True)
        self._window.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            self._window,
            text=self.text,
            bg="#1e1c19",
            fg="#f4ecdd",
            relief="solid",
            borderwidth=1,
            padx=8,
            pady=4,
            font=("Bahnschrift", 9),
        )
        label.pack()

    def _hide(self, _event=None) -> None:
        if self._window is None:
            return
        self._window.destroy()
        self._window = None


class FloatingShellApp:
    """Tkinter-based floating shell for end-user interaction."""

    def __init__(self, controller: FloatingShellController) -> None:
        self.controller = controller
        self.root = tk.Tk()
        self.root.title("Aradhya")
        self.root.configure(bg="#f4ecdd")
        self.root.geometry("560x420")
        self.root.minsize(520, 360)
        try:
            self.root.wm_attributes("-topmost", True)
        except tk.TclError:
            logger.debug("Could not force topmost mode for floating shell")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._button_refs: dict[str, tk.Button] = {}
        self._entry_var = tk.StringVar()

        self._build_layout()
        self._append_output(
            "Aradhya > Floating shell ready. Local-only mode is active; cloud features are off."
        )
        self._update_visual_state()

    def run(self) -> None:
        self.root.mainloop()

    def _build_layout(self) -> None:
        header = tk.Frame(self.root, bg="#f4ecdd")
        header.pack(fill="x", padx=14, pady=(14, 10))

        title = tk.Label(
            header,
            text="ARADHYA",
            bg="#f4ecdd",
            fg="#26211b",
            font=("Bahnschrift SemiBold", 18),
        )
        title.pack(side="left")

        badge = tk.Label(
            header,
            text="LOCAL",
            bg="#d9c8a7",
            fg="#2f271d",
            padx=10,
            pady=4,
            font=("Bahnschrift", 9),
        )
        badge.pack(side="right")

        controls = tk.Frame(self.root, bg="#f4ecdd")
        controls.pack(fill="x", padx=14, pady=(0, 10))

        palette = {
            "mic": "#0f766e",
            "screen": "#8b5e34",
            "advanced": "#b45309",
            "interaction": "#3f3f46",
        }
        for spec in self.controller.control_specs():
            button = tk.Button(
                controls,
                text=spec.label,
                width=10,
                bg=palette.get(spec.control_id, "#57534e"),
                fg="#fffaf0",
                relief="raised",
                activebackground=palette.get(spec.control_id, "#57534e"),
                activeforeground="#fffaf0",
                font=("Bahnschrift SemiBold", 11),
                command=lambda control_id=spec.control_id: self._on_control_pressed(control_id),
            )
            button.pack(side="left", padx=(0, 8))
            _Tooltip(button, spec.tooltip)
            self._button_refs[spec.control_id] = button

        self._status_label = tk.Label(
            self.root,
            text=self.controller.status_line(),
            anchor="w",
            justify="left",
            bg="#f4ecdd",
            fg="#5c4a37",
            font=("Bahnschrift", 9),
        )
        self._status_label.pack(fill="x", padx=14, pady=(0, 10))

        self._output = scrolledtext.ScrolledText(
            self.root,
            wrap="word",
            height=14,
            bg="#fffaf0",
            fg="#2f271d",
            insertbackground="#2f271d",
            relief="solid",
            borderwidth=1,
            font=("Bahnschrift", 10),
        )
        self._output.pack(fill="both", expand=True, padx=14, pady=(0, 10))
        self._output.configure(state="disabled")

        input_row = tk.Frame(self.root, bg="#f4ecdd")
        input_row.pack(fill="x", padx=14, pady=(0, 14))

        self._entry = tk.Entry(
            input_row,
            textvariable=self._entry_var,
            bg="#fffaf0",
            fg="#2f271d",
            insertbackground="#2f271d",
            relief="solid",
            borderwidth=1,
            font=("Bahnschrift", 11),
        )
        self._entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._entry.bind("<Return>", self._on_send)

        send_button = tk.Button(
            input_row,
            text="Send",
            width=10,
            bg="#2f6f4f",
            fg="#fffaf0",
            activebackground="#2f6f4f",
            activeforeground="#fffaf0",
            font=("Bahnschrift SemiBold", 11),
            command=self._on_send,
        )
        send_button.pack(side="right")

    def _append_output(self, line: str) -> None:
        self._output.configure(state="normal")
        self._output.insert("end", line + "\n")
        self._output.configure(state="disabled")
        self._output.see("end")

    def _append_lines(self, lines: tuple[str, ...]) -> None:
        for line in lines:
            self._append_output(line)
        self._update_visual_state()

    def _on_control_pressed(self, control_id: str) -> None:
        if control_id == "interaction":
            self._append_output(self.controller.toggle_interaction())
            self._update_visual_state()
            return

        if control_id == "advanced":
            self._append_output(self.controller.arm_advanced_request())
            self._update_visual_state()
            return

        if control_id == "screen":
            screenshot_path: Path | None = None
            if not self.controller.shell_state_snapshot().screen_context_active:
                selection = filedialog.askopenfilename(
                    title="Attach a screenshot (optional)",
                    filetypes=(
                        ("Images", "*.png *.jpg *.jpeg *.bmp *.gif"),
                        ("All files", "*.*"),
                    ),
                )
                if selection:
                    screenshot_path = Path(selection)
            self._append_output(self.controller.toggle_screen_context(screenshot_path))
            if self.controller.shell_state_snapshot().screen_context_active and not self._entry_var.get():
                self._entry_var.set("Help me with what is on screen: ")
                self._entry.icursor("end")
            self._update_visual_state()
            return

        if control_id == "mic":
            self._run_in_background(self.controller.capture_once)

    def _on_send(self, _event=None) -> None:
        text = self._entry_var.get()
        self._entry_var.set("")
        self._append_lines(self.controller.submit_text(text))

    def _run_in_background(self, callback: Callable[[], tuple[str, ...]]) -> None:
        def worker() -> None:
            lines = callback()
            self.root.after(0, lambda: self._append_lines(lines))

        threading.Thread(target=worker, daemon=True).start()

    def _update_visual_state(self) -> None:
        snapshot = self.controller.shell_state_snapshot()
        self._status_label.configure(text=self.controller.status_line())

        interaction_button = self._button_refs["interaction"]
        interaction_button.configure(bg="#2f6f4f" if snapshot.interaction_enabled else "#3f3f46")

        advanced_button = self._button_refs["advanced"]
        advanced_button.configure(relief="sunken" if snapshot.advanced_next_request else "raised")

        screen_button = self._button_refs["screen"]
        screen_button.configure(relief="sunken" if snapshot.screen_context_active else "raised")

    def _on_close(self) -> None:
        self.root.destroy()


def create_floating_shell_controller(project_root: Path | None = None) -> FloatingShellController:
    """Construct the floating-shell controller for the current project."""

    root = project_root or PROJECT_ROOT
    runtime_profile = load_runtime_profile(root)
    model_provider = build_text_model_provider(runtime_profile.model)
    assistant = AradhyaAssistant.from_project_root(
        project_root=root,
        model_provider=model_provider,
    )
    voice_manager = VoiceInboxManager(runtime_profile.voice)
    return FloatingShellController(
        assistant=assistant,
        runtime_profile=runtime_profile,
        voice_manager=voice_manager,
    )


def main() -> None:
    """Start the floating-shell entrypoint."""

    configure_logging(PROJECT_ROOT)
    controller = create_floating_shell_controller(PROJECT_ROOT)
    app = FloatingShellApp(controller)
    app.run()


if __name__ == "__main__":
    main()
