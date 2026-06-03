import json
from unittest.mock import MagicMock, patch


from aradhya.setup_wizard import (
    _confirm,
    _detect_ollama_models,
    _detect_ollama_running,
    _load_json,
    _prompt,
    _save_json,
    run_wizard,
    step_execution,
    step_finish,
    step_model,
    step_user_context,
    step_voice,
    step_welcome,
)


def test_load_json_existing_file(tmp_path):
    file_path = tmp_path / "test.json"
    file_path.write_text('{"key": "value"}', encoding="utf-8")
    assert _load_json(file_path) == {"key": "value"}


def test_load_json_missing_file(tmp_path):
    file_path = tmp_path / "missing.json"
    assert _load_json(file_path) == {}


def test_save_json(tmp_path):
    file_path = tmp_path / "subdir" / "test.json"
    _save_json(file_path, {"key": "value"})
    assert file_path.is_file()
    assert json.loads(file_path.read_text(encoding="utf-8")) == {"key": "value"}


@patch("aradhya.setup_wizard.console.input")
def test_prompt_with_input(mock_input):
    mock_input.return_value = "my answer  "
    assert _prompt("Question?") == "my answer"


@patch("aradhya.setup_wizard.console.input")
def test_prompt_empty_with_default(mock_input):
    mock_input.return_value = "  "
    assert _prompt("Question?", default="def") == "def"


@patch("aradhya.setup_wizard.console.input")
def test_confirm_yes(mock_input):
    mock_input.return_value = " y "
    assert _confirm("Question?") is True

    mock_input.return_value = "yes"
    assert _confirm("Question?") is True


@patch("aradhya.setup_wizard.console.input")
def test_confirm_no(mock_input):
    mock_input.return_value = " n "
    assert _confirm("Question?") is False

    mock_input.return_value = "no"
    assert _confirm("Question?") is False


@patch("aradhya.setup_wizard.console.input")
def test_confirm_empty_with_default(mock_input):
    mock_input.return_value = ""
    assert _confirm("Question?", default=True) is True

    mock_input.return_value = ""
    assert _confirm("Question?", default=False) is False


@patch("subprocess.run")
def test_detect_ollama_models_success(mock_run):
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "NAME      ID      SIZE\nmodel1    123     1GB\nmodel2    456     2GB"
    mock_run.return_value = mock_result

    models = _detect_ollama_models()
    assert models == ["model1", "model2"]


@patch("subprocess.run")
def test_detect_ollama_models_failure(mock_run):
    mock_run.side_effect = FileNotFoundError()
    assert _detect_ollama_models() == []


@patch("requests.get")
def test_detect_ollama_running_success(mock_get):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_get.return_value = mock_response
    assert _detect_ollama_running() is True


@patch("requests.get")
def test_detect_ollama_running_failure(mock_get):
    mock_get.side_effect = Exception("Connection error")
    assert _detect_ollama_running() is False


@patch("aradhya.setup_wizard.console.print")
def test_step_welcome(mock_print):
    step_welcome()
    assert mock_print.called


@patch("aradhya.setup_wizard._detect_ollama_running", return_value=True)
@patch("aradhya.setup_wizard._detect_ollama_models", return_value=["gemma4:e4b", "llama3"])
@patch("aradhya.setup_wizard._prompt")
@patch("aradhya.setup_wizard._confirm", return_value=False)
def test_step_model_ollama_running(mock_confirm, mock_prompt, mock_detect_models, mock_detect_running):
    # simulate user selecting model index 1 ("gemma4:e4b") and default base URL
    mock_prompt.side_effect = ["1", "http://127.0.0.1:11434"]
    profile = {}

    updated_profile = step_model(profile)
    assert updated_profile["model"]["model_name"] == "gemma4:e4b"
    assert updated_profile["model"]["base_url"] == "http://127.0.0.1:11434"
    assert updated_profile["model"]["provider"] == "ollama"
    assert "system_prompt" in updated_profile["model"]


@patch("aradhya.setup_wizard._confirm")
@patch("aradhya.setup_wizard._prompt")
def test_step_voice_enabled(mock_prompt, mock_confirm):
    mock_confirm.side_effect = [True, True]  # enable_voice, enabled_on_startup
    mock_prompt.side_effect = ["faster_whisper", "small", "cuda"]

    profile = {}
    updated_profile = step_voice(profile)

    assert updated_profile["voice"]["provider"] == "faster_whisper"
    assert updated_profile["voice"]["faster_whisper_model_size"] == "small"
    assert updated_profile["voice"]["faster_whisper_device"] == "cuda"
    assert updated_profile["voice_activation"]["enabled_on_startup"] is True


@patch("aradhya.setup_wizard._confirm", return_value=False)
def test_step_voice_disabled(mock_confirm):
    profile = {}
    updated_profile = step_voice(profile)

    assert updated_profile["voice"]["provider"] == "manual_transcript"
    assert updated_profile["voice_activation"]["enabled_on_startup"] is False


@patch("aradhya.setup_wizard.USER_NOTES_PATH")
@patch("aradhya.setup_wizard.USER_RULES_PATH")
@patch("aradhya.setup_wizard._prompt")
def test_step_user_context_new(mock_prompt, mock_rules_path, mock_notes_path):
    mock_notes_path.is_file.return_value = False
    mock_rules_path.is_file.return_value = False

    mock_prompt.side_effect = ["Alice", "Developer", "Coding"]

    step_user_context()

    assert mock_notes_path.write_text.called
    written_notes = mock_notes_path.write_text.call_args[0][0]
    assert "Name: Alice" in written_notes
    assert "Role: Developer" in written_notes
    assert "Primary use: Coding" in written_notes

    assert mock_rules_path.write_text.called


@patch("aradhya.setup_wizard._confirm", return_value=True)
def test_step_execution_careful(mock_confirm):
    preferences = {}
    updated_prefs = step_execution(preferences)
    assert updated_prefs["execution_policy"] == "careful"


@patch("aradhya.setup_wizard._confirm", return_value=False)
def test_step_execution_dry_run(mock_confirm):
    preferences = {}
    updated_prefs = step_execution(preferences)
    assert updated_prefs["execution_policy"] == "dry_run"


@patch("aradhya.setup_wizard._save_json")
@patch("aradhya.setup_wizard.console.print")
def test_step_finish(mock_print, mock_save_json):
    profile = {"model": {"model_name": "test-model"}}
    preferences = {"execution_policy": "careful"}

    step_finish(profile, preferences)

    assert mock_save_json.call_count == 2
    assert mock_print.call_count == 2


@patch("aradhya.setup_wizard.step_finish")
@patch("aradhya.setup_wizard.step_execution", return_value={})
@patch("aradhya.setup_wizard.step_user_context")
@patch("aradhya.setup_wizard.step_voice", return_value={})
@patch("aradhya.setup_wizard.step_model", return_value={})
@patch("aradhya.setup_wizard._load_json", return_value={})
@patch("aradhya.setup_wizard.step_welcome")
def test_run_wizard(mock_welcome, mock_load, mock_model, mock_voice, mock_context, mock_exec, mock_finish):
    run_wizard()

    mock_welcome.assert_called_once()
    assert mock_load.call_count == 2
    mock_model.assert_called_once()
    mock_voice.assert_called_once()
    mock_context.assert_called_once()
    mock_exec.assert_called_once()
    mock_finish.assert_called_once()
