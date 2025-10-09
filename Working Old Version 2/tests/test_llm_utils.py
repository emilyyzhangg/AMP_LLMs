import pytest
from unittest import mock
from llm_utils import (
    check_ollama_installed,
    get_available_models,
    ensure_model_available,
    choose_model,
    clean_ollama_output,
    run_ollama
)

# ------------------------
# check_ollama_installed
# ------------------------
def test_check_ollama_installed_success():
    mock_ssh = mock.Mock()
    mock_stdout = mock.Mock()
    mock_stdout.read.return_value = b"/usr/local/bin/ollama\n"
    mock_ssh.exec_command.return_value = (None, mock_stdout, None)

    check_ollama_installed(mock_ssh)  # Should not raise

def test_check_ollama_installed_not_found():
    mock_ssh = mock.Mock()
    mock_stdout = mock.Mock()
    mock_stdout.read.return_value = b""
    mock_ssh.exec_command.return_value = (None, mock_stdout, None)

    with pytest.raises(EnvironmentError):
        check_ollama_installed(mock_ssh)

# ------------------------
# get_available_models
# ------------------------
def test_get_available_models_returns_models():
    mock_ssh = mock.Mock()
    mock_stdout = mock.Mock()
    mock_stdout.read.return_value = b"""
NAME            SIZE    MODIFIED
llama2          3.8GB   2024-09-01
mistral         4.2GB   2024-08-15
    """
    mock_ssh.exec_command.return_value = (None, mock_stdout, None)

    models = get_available_models(mock_ssh)
    assert models == ["llama2", "mistral"]

def test_get_available_models_empty_list():
    mock_ssh = mock.Mock()
    mock_stdout = mock.Mock()
    mock_stdout.read.return_value = b""
    mock_ssh.exec_command.return_value = (None, mock_stdout, None)

    models = get_available_models(mock_ssh)
    assert models == []

# ------------------------
# ensure_model_available
# ------------------------
@mock.patch("llm_utils.time.sleep", return_value=None)
@mock.patch("llm_utils.get_available_models", return_value=["mistral"])
def test_ensure_model_available_already_present(mock_get, mock_sleep):
    mock_ssh = mock.Mock()
    ensure_model_available(mock_ssh, "mistral")
    mock_ssh.exec_command.assert_not_called()

@mock.patch("llm_utils.time.sleep", return_value=None)
@mock.patch("llm_utils.get_available_models", return_value=["llama2"])
def test_ensure_model_available_needs_pull(mock_get, mock_sleep):
    mock_ssh = mock.Mock()

    stdout_mock = mock.Mock()
    stdout_mock.read.return_value = b"Pulled model successfully\n"
    stderr_mock = mock.Mock()
    stderr_mock.read.return_value = b""

    mock_ssh.exec_command.return_value = (None, stdout_mock, stderr_mock)

    ensure_model_available(mock_ssh, "mistral")
    mock_ssh.exec_command.assert_called()

# ------------------------
# choose_model
# ------------------------
@mock.patch("builtins.input", side_effect=["2"])
def test_choose_model_valid_choice(mock_input):
    models = ["llama2", "mistral", "phi"]
    chosen = choose_model(models)
    assert chosen == "mistral"

@mock.patch("builtins.input", side_effect=["exit"])
def test_choose_model_exit(mock_input):
    models = ["llama2"]
    assert choose_model(models) is None

@mock.patch("builtins.input", side_effect=["99", "1"])
def test_choose_model_invalid_then_valid(mock_input):
    models = ["llama2", "mistral"]
    chosen = choose_model(models)
    assert chosen == "llama2"

# ------------------------
# clean_ollama_output
# ------------------------
def test_clean_ollama_output_strips_text():
    raw = "  some response with whitespace \n"
    assert clean_ollama_output(raw) == "some response with whitespace"

# ------------------------
# run_ollama
# ------------------------
def test_run_ollama_returns_output():
    mock_ssh = mock.Mock()
    stdin = mock.Mock()
    stdout = mock.Mock()
    stderr = mock.Mock()

    stdin.write = mock.Mock()
    stdin.flush = mock.Mock()
    stdin.channel.shutdown_write = mock.Mock()

    stdout.read.return_value = b"This is the output"
    stderr.read.return_value = b""

    mock_ssh.exec_command.return_value = (stdin, stdout, stderr)

    result = run_ollama(mock_ssh, "llama2", "Tell me a joke")
    assert result == "This is the output"
    stdin.write.assert_called_once()
