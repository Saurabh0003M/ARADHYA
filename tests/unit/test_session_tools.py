from __future__ import annotations


import pytest

from src.aradhya.tools.session_tools import save_note, recall_note, list_notes

@pytest.fixture
def mock_notes_dir(tmp_path, monkeypatch):
    """Fixture to mock the notes directory."""
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir()

    # We patch the _resolve_notes_dir import within session_tools
    monkeypatch.setattr("src.aradhya.tools.session_tools._resolve_notes_dir", lambda: notes_dir)
    return notes_dir

def test_save_note_success(mock_notes_dir):
    result = save_note(title="My First Note", content="This is the content.")

    assert "Note saved" in result

    expected_path = mock_notes_dir / "My First Note.md"
    assert expected_path.exists()

    content = expected_path.read_text(encoding="utf-8")
    assert "# My First Note" in content
    assert "This is the content." in content

def test_save_note_special_chars(mock_notes_dir):
    result = save_note(title="Note @#% with/special:chars!", content="Content")

    assert "Note saved" in result

    expected_path = mock_notes_dir / "Note ___ with_special_chars_.md"
    assert expected_path.exists()

def test_save_note_error(monkeypatch):
    # Mock to throw an error when writing
    def mock_resolve():
        class MockPath:
            def __truediv__(self, other):
                return self
            def write_text(self, *args, **kwargs):
                raise PermissionError("Access denied")
        return MockPath()

    monkeypatch.setattr("src.aradhya.tools.session_tools._resolve_notes_dir", mock_resolve)

    result = save_note("Test", "Content")
    assert "Error saving note: Access denied" in result

def test_recall_note_exact_match(mock_notes_dir):
    save_note("Exact Match", "Exact Content")

    result = recall_note("Exact Match")
    assert "# Exact Match" in result
    assert "Exact Content" in result

def test_recall_note_fuzzy_match(mock_notes_dir):
    save_note("Complex Note Title", "Fuzzy Content")

    # Test fuzzy matching
    result = recall_note("complex")
    assert "# Complex Note Title" in result
    assert "Fuzzy Content" in result

def test_recall_note_not_found(mock_notes_dir):
    result = recall_note("Nonexistent")
    assert result == "No note found matching 'Nonexistent'."

def test_recall_note_no_directory(tmp_path, monkeypatch):
    non_existent_dir = tmp_path / "does_not_exist"
    monkeypatch.setattr("src.aradhya.tools.session_tools._resolve_notes_dir", lambda: non_existent_dir)

    result = recall_note("Anything")
    assert result == "No notes directory found."

def test_list_notes_empty(mock_notes_dir):
    result = list_notes()
    assert result == "No notes saved yet."

def test_list_notes_with_items(mock_notes_dir):
    save_note("Alpha", "Content A")
    save_note("Beta", "Content B")
    save_note("Gamma", "Content C")

    result = list_notes()
    assert "Saved notes (3):" in result
    assert "- Alpha" in result
    assert "- Beta" in result
    assert "- Gamma" in result

def test_list_notes_no_directory(tmp_path, monkeypatch):
    non_existent_dir = tmp_path / "does_not_exist"
    monkeypatch.setattr("src.aradhya.tools.session_tools._resolve_notes_dir", lambda: non_existent_dir)

    result = list_notes()
    assert result == "No notes directory found."
