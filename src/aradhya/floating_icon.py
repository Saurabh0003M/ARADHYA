"""Standalone draggable floating icon with an expandable menu."""

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

        self.root.configure(bg="#2D2D2D")
        self.label = tk.Label(
            self.root,
            text="A",
            fg="white",
            bg="#2D2D2D",
            font=("Segoe UI", 20, "bold"),
            cursor="hand2"
        )
        self.label.pack(expand=True, fill="both")

        self._offset_x = 0
        self._offset_y = 0
        self._is_dragging = False

        self.label.bind("<ButtonPress-1>", self.on_press)
        self.label.bind("<B1-Motion>", self.on_drag)
        self.label.bind("<ButtonRelease-1>", self.on_release)

        # Create the popup menu
        self.menu = tk.Menu(self.root, tearoff=0, bg="#333333", fg="white", activebackground="#555555")
        self.menu.add_command(label="Wake Aradhya", command=lambda: self.send_command("wake"))
        self.menu.add_command(label="Sleep Aradhya", command=lambda: self.send_command("sleep"))
        self.menu.add_command(label="Toggle Voice Listen", command=lambda: self.send_command("voice_toggle"))
        self.menu.add_separator()
        self.menu.add_command(label="Close Icon", command=lambda: self.send_command("exit_icon"))

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
