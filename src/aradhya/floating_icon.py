"""Standalone draggable floating icon with an expandable menu.

The icon lives in the system tray area and sends IPC commands to the
main Aradhya process (or the daemon) via a simple file-based protocol.

Enhanced with quick-access buttons for:
  - Microphone (toggle voice capture)
  - Camera (toggle screen watch)
  - Screen Share (toggle browser/screen capture)
  - 'A' Debate AI activation toggle
"""

import sys
import tkinter as tk
from pathlib import Path

# We use a simple IPC file in the project root to send commands to main.py
PROJECT_ROOT = Path(__file__).resolve().parents[2]
IPC_FILE = PROJECT_ROOT / ".aradhya_ipc"

# ── Color palette ─────────────────────────────────────────────────────
BG_DARK = "#0d1117"
BG_PANEL = "#161b22"
BG_BUTTON = "#21262d"
BG_HOVER = "#30363d"
FG_TEAL = "#00d4aa"
FG_TEXT = "#c9d1d9"
FG_DIM = "#7f848e"
FG_RED = "#f85149"
FG_AMBER = "#d29922"
FG_BLUE = "#58a6ff"
FG_PURPLE = "#bc8cff"


class FloatingIcon:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.95)

        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()

        # Panel dimensions (compact vertical strip)
        self.panel_width = 54
        self.panel_height = 290
        self.root.geometry(
            f"{self.panel_width}x{self.panel_height}"
            f"+{screen_width - 80}+{screen_height - self.panel_height - 80}"
        )
        self.root.configure(bg=BG_DARK)

        # ── Drag state ────────────────────────────────────────────────
        self._offset_x = 0
        self._offset_y = 0
        self._is_dragging = False

        # ── Toggle states ─────────────────────────────────────────────
        self._mic_active = False
        self._camera_active = False
        self._screenshare_active = False
        self._debate_active = False
        self._is_awake = True

        # ── Build UI ──────────────────────────────────────────────────
        self._build_panel()

        # Context menu for additional options
        self.menu = tk.Menu(
            self.root, tearoff=0,
            bg=BG_PANEL, fg=FG_TEXT,
            activebackground=BG_HOVER, activeforeground=FG_TEAL,
            font=("Segoe UI", 10),
            relief="flat", bd=0,
        )
        self._build_context_menu()

    def _make_button(self, parent, text, color, command, tooltip=""):
        """Create a styled circular-ish button."""
        btn = tk.Label(
            parent,
            text=text,
            fg=color,
            bg=BG_BUTTON,
            font=("Segoe UI", 14),
            width=3,
            height=1,
            cursor="hand2",
            relief="flat",
        )
        btn.pack(pady=3, padx=4)
        btn.bind("<Enter>", lambda e: btn.configure(bg=BG_HOVER))
        btn.bind("<Leave>", lambda e: btn.configure(
            bg=self._active_bg(btn) if hasattr(btn, "_active") and btn._active else BG_BUTTON
        ))
        btn.bind("<ButtonRelease-1>", lambda e: command())
        btn._active = False
        return btn

    def _active_bg(self, btn):
        return BG_HOVER if getattr(btn, "_active", False) else BG_BUTTON

    def _build_panel(self):
        """Build the vertical button strip."""
        # Main logo / drag handle at top
        self.logo = tk.Label(
            self.root,
            text="A",
            fg=FG_TEAL,
            bg=BG_DARK,
            font=("Segoe UI", 18, "bold"),
            cursor="fleur",  # move cursor
        )
        self.logo.pack(pady=(8, 4))
        self.logo.bind("<ButtonPress-1>", self.on_press)
        self.logo.bind("<B1-Motion>", self.on_drag)
        self.logo.bind("<ButtonRelease-1>", self.on_release)

        # Separator
        sep = tk.Frame(self.root, bg=BG_HOVER, height=1)
        sep.pack(fill="x", padx=8, pady=2)

        # ── Quick-access buttons ──────────────────────────────────────

        # 🎤 Microphone toggle
        self.btn_mic = self._make_button(
            self.root, "🎤", FG_DIM, self._toggle_mic,
            tooltip="Toggle microphone",
        )

        # 📷 Camera / Screen Watch toggle
        self.btn_camera = self._make_button(
            self.root, "📷", FG_DIM, self._toggle_camera,
            tooltip="Toggle screen watch",
        )

        # 🖥️ Screen Share toggle
        self.btn_screen = self._make_button(
            self.root, "🖥", FG_DIM, self._toggle_screenshare,
            tooltip="Toggle screen share",
        )

        # Separator
        sep2 = tk.Frame(self.root, bg=BG_HOVER, height=1)
        sep2.pack(fill="x", padx=8, pady=2)

        # 🅰️ Debate AI toggle
        self.btn_debate = self._make_button(
            self.root, "A", FG_DIM, self._toggle_debate,
            tooltip="Toggle Debate AI",
        )
        self.btn_debate.configure(font=("Segoe UI", 14, "bold"))

        # Separator
        sep3 = tk.Frame(self.root, bg=BG_HOVER, height=1)
        sep3.pack(fill="x", padx=8, pady=2)

        # ⋮ More options (right-click menu)
        self.btn_more = self._make_button(
            self.root, "⋮", FG_DIM, self._show_menu,
            tooltip="More options",
        )

    def _build_context_menu(self):
        """Build the expanded context menu."""
        self.menu.delete(0, "end")

        self.menu.add_command(
            label="⚡ Wake Aradhya",
            command=lambda: self.send_command("wake"),
        )
        self.menu.add_command(
            label="😴 Sleep Aradhya",
            command=lambda: self.send_command("sleep"),
        )
        self.menu.add_separator()
        self.menu.add_command(
            label="🔒 Lock Screen",
            command=lambda: self.send_command("lock_screen"),
        )
        self.menu.add_command(
            label="☕ Keep Awake",
            command=lambda: self.send_command("prevent_sleep"),
        )
        self.menu.add_separator()
        self.menu.add_command(
            label="❌ Close Icon",
            command=lambda: self.send_command("exit_icon"),
        )

    # ── Toggle handlers ───────────────────────────────────────────────

    def _toggle_mic(self):
        self._mic_active = not self._mic_active
        if self._mic_active:
            self.btn_mic.configure(fg=FG_RED, bg=BG_HOVER)
            self.btn_mic._active = True
        else:
            self.btn_mic.configure(fg=FG_DIM, bg=BG_BUTTON)
            self.btn_mic._active = False
        self.send_command("voice_toggle")

    def _toggle_camera(self):
        self._camera_active = not self._camera_active
        if self._camera_active:
            self.btn_camera.configure(fg=FG_RED, bg=BG_HOVER)
            self.btn_camera._active = True
        else:
            self.btn_camera.configure(fg=FG_DIM, bg=BG_BUTTON)
            self.btn_camera._active = False
        self.send_command("screen_watch_toggle")

    def _toggle_screenshare(self):
        self._screenshare_active = not self._screenshare_active
        if self._screenshare_active:
            self.btn_screen.configure(fg=FG_BLUE, bg=BG_HOVER)
            self.btn_screen._active = True
        else:
            self.btn_screen.configure(fg=FG_DIM, bg=BG_BUTTON)
            self.btn_screen._active = False
        self.send_command("browser_toggle")

    def _toggle_debate(self):
        self._debate_active = not self._debate_active
        if self._debate_active:
            self.btn_debate.configure(fg=FG_PURPLE, bg=BG_HOVER)
            self.btn_debate._active = True
            # Change main logo to indicate Debate mode
            self.logo.configure(fg=FG_PURPLE)
        else:
            self.btn_debate.configure(fg=FG_DIM, bg=BG_BUTTON)
            self.btn_debate._active = False
            self.logo.configure(fg=FG_TEAL)
        self.send_command("debate_toggle")

    # ── Menu ──────────────────────────────────────────────────────────

    def _show_menu(self):
        x = self.root.winfo_x() - 150
        y = self.root.winfo_y()
        self.menu.tk_popup(x, y)

    # ── IPC ───────────────────────────────────────────────────────────

    def send_command(self, cmd: str):
        try:
            IPC_FILE.write_text(cmd, encoding="utf-8")
        except Exception as e:
            print(f"Failed to send command {cmd}: {e}")

        if cmd == "exit_icon":
            self.root.destroy()

    # ── Drag handling ─────────────────────────────────────────────────

    def on_press(self, event):
        self._offset_x = event.x
        self._offset_y = event.y
        self._is_dragging = False

    def on_drag(self, event):
        self._is_dragging = True
        x = self.root.winfo_pointerx() - self._offset_x
        y = self.root.winfo_pointery() - self._offset_y
        self.root.geometry(f"+{x}+{y}")

    def on_release(self, event):
        if not self._is_dragging:
            # Click on logo = toggle wake/sleep
            self._is_awake = not self._is_awake
            if self._is_awake:
                self.logo.configure(
                    fg=FG_PURPLE if self._debate_active else FG_TEAL,
                )
                self.send_command("wake")
            else:
                self.logo.configure(fg=FG_AMBER)
                self.send_command("sleep")


def main():
    root = tk.Tk()
    root.title("Aradhya")
    app = FloatingIcon(root)
    root.mainloop()


if __name__ == "__main__":
    main()
