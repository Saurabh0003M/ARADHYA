"""Standalone draggable floating icon with an expandable menu.

The icon lives in the system tray area and sends IPC commands to the
main Aradhya process (or the daemon) via a simple file-based protocol.
"""

import sys
import tkinter as tk
from pathlib import Path

# We use a simple IPC file in the project root to send commands to main.py
PROJECT_ROOT = Path(__file__).resolve().parents[2]
IPC_FILE = PROJECT_ROOT / ".aradhya_ipc"


class FloatingIcon:
    def __init__(self, root):
        self.root = root
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)

        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        self.root.geometry(f"50x50+{screen_width - 100}+{screen_height - 150}")

        self.root.configure(bg="#1a1a2e")
        self.label = tk.Label(
            self.root,
            text="A",
            fg="#00d4aa",
            bg="#1a1a2e",
            font=("Segoe UI", 20, "bold"),
            cursor="hand2"
        )
        self.label.pack(expand=True, fill="both")

        self._offset_x = 0
        self._offset_y = 0
        self._is_dragging = False

        # Toggle states
        self._screen_watch = False
        self._browser_active = False

        self.label.bind("<ButtonPress-1>", self.on_press)
        self.label.bind("<B1-Motion>", self.on_drag)
        self.label.bind("<ButtonRelease-1>", self.on_release)

        # Create the popup menu
        self.menu = tk.Menu(
            self.root, tearoff=0,
            bg="#16213e", fg="#e0e0e0",
            activebackground="#0f3460", activeforeground="#00d4aa",
            font=("Segoe UI", 10),
            relief="flat", bd=0,
        )
        self._build_menu()

    def _build_menu(self):
        """Build the right-click context menu with all controls."""
        self.menu.delete(0, "end")

        # ─── Core controls ───
        self.menu.add_command(
            label="⚡ Wake Aradhya",
            command=lambda: self.send_command("wake"),
        )
        self.menu.add_command(
            label="😴 Sleep Aradhya",
            command=lambda: self.send_command("sleep"),
        )
        self.menu.add_separator()

        # ─── Voice ───
        self.menu.add_command(
            label="🎙️ Toggle Voice Listen",
            command=lambda: self.send_command("voice_toggle"),
        )
        self.menu.add_separator()

        # ─── Screen & Browser toggles ───
        screen_label = "📷 Screen Watch: ON" if self._screen_watch else "📷 Screen Watch: OFF"
        self.menu.add_command(
            label=screen_label,
            command=self._toggle_screen_watch,
        )

        browser_label = "🌐 Browser: ACTIVE" if self._browser_active else "🌐 Browser: OFF"
        self.menu.add_command(
            label=browser_label,
            command=self._toggle_browser,
        )

        self.menu.add_separator()

        # ─── Power controls ───
        self.menu.add_command(
            label="🔒 Lock Screen",
            command=lambda: self.send_command("lock_screen"),
        )
        self.menu.add_command(
            label="☕ Keep Awake",
            command=lambda: self.send_command("prevent_sleep"),
        )
        self.menu.add_separator()

        # ─── Exit ───
        self.menu.add_command(
            label="❌ Close Icon",
            command=lambda: self.send_command("exit_icon"),
        )

    def _toggle_screen_watch(self):
        self._screen_watch = not self._screen_watch
        self.send_command("screen_watch_toggle")
        self._build_menu()  # Rebuild to update label
        # Visual indicator: change icon color when screen watch is active
        if self._screen_watch:
            self.label.configure(fg="#ff6b6b")  # Red = watching
        else:
            self.label.configure(fg="#00d4aa")  # Teal = normal

    def _toggle_browser(self):
        self._browser_active = not self._browser_active
        self.send_command("browser_toggle")
        self._build_menu()

    def send_command(self, cmd: str):
        try:
            IPC_FILE.write_text(cmd, encoding="utf-8")
        except Exception as e:
            print(f"Failed to send command {cmd}: {e}")

        if cmd == "exit_icon":
            self.root.destroy()

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
            # It was a click, show menu
            try:
                self.menu.tk_popup(event.x_root, event.y_root)
            finally:
                self.menu.grab_release()

def main():
    root = tk.Tk()
    app = FloatingIcon(root)
    root.mainloop()

if __name__ == "__main__":
    main()
