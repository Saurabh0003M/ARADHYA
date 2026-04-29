"""Session and notes tools for the agent loop.

These tools let the model interact with the session manager and the
user's persistent notes.
"""

from __future__ import annotations

from pathlib import Path

from src.aradhya.tools.tool_registry import tool_definition

NOTES_DIR = Path.home() / ".aradhya" / "notes"


@tool_definition(
    name="save_note",
    description="Save a persistent note that can be recalled later.",
    parameters={
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Short title for the note.",
            },
            "content": {
                "type": "string",
                "description": "Content of the note.",
            },
        },
        "required": ["title", "content"],
    },
)
def save_note(title: str, content: str) -> str:
    """Save a note to the user's notes directory."""
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in title)
    note_path = NOTES_DIR / f"{safe_name.strip()}.md"
    try:
        note_path.write_text(
            f"# {title}\n\n{content}\n",
            encoding="utf-8",
        )
        return f"Note saved: {note_path}"
    except Exception as error:
        return f"Error saving note: {error}"


@tool_definition(
    name="recall_note",
    description="Recall a previously saved note by title.",
    parameters={
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Title or filename of the note to recall.",
            },
        },
        "required": ["title"],
    },
)
def recall_note(title: str) -> str:
    """Recall a note from the user's notes directory."""
    if not NOTES_DIR.is_dir():
        return "No notes directory found."

    safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in title)
    note_path = NOTES_DIR / f"{safe_name.strip()}.md"

    if note_path.is_file():
        return note_path.read_text(encoding="utf-8")

    # Fuzzy match
    matches = [
        p for p in NOTES_DIR.glob("*.md")
        if title.lower() in p.stem.lower()
    ]
    if matches:
        return matches[0].read_text(encoding="utf-8")

    return f"No note found matching '{title}'."


@tool_definition(
    name="list_notes",
    description="List all saved notes.",
    parameters={"type": "object", "properties": {}},
)
def list_notes() -> str:
    """List all notes in the user's notes directory."""
    if not NOTES_DIR.is_dir():
        return "No notes directory found."

    notes = sorted(NOTES_DIR.glob("*.md"))
    if not notes:
        return "No notes saved yet."

    lines = [f"Saved notes ({len(notes)}):\n"]
    for note in notes:
        lines.append(f"  - {note.stem}")
    return "\n".join(lines)


ALL_SESSION_TOOLS = [save_note, recall_note, list_notes]
