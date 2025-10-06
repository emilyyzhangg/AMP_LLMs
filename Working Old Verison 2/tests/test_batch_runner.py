import pytest
from unittest import mock
from io import StringIO
import builtins

from batch_runner import run_batch, run_prompts_from_csv


# --------- Helper Fixtures & Mocks ---------

@pytest.fixture
def mock_ssh_client():
    mock_client = mock.Mock()

    stdin = mock.Mock()
    stdout = mock.Mock()
    stderr = mock.Mock()

    stdin.write = mock.Mock()
    stdin.flush = mock.Mock()
    stdin.channel.shutdown_write = mock.Mock()

    stdout.read.return_value = b"Mock LLM output"
    stderr.read.return_value = b""

    mock_client.exec_command.return_value = (stdin, stdout, stderr)
    return mock_client


@mock.patch("batch_runner.clean_ollama_output", return_value="Cleaned Output")
def test_run_batch_valid_csv(mock_clean, tmp_path, mock_ssh_client):
    # Create a temporary CSV file with prompts
    csv_path = tmp_path / "test_prompts.csv"
    csv_path.write_text("prompt\nHello world\nTest prompt\n", encoding='utf-8')

    results = run_batch(str(csv_path), "llama2", ssh_client=mock_ssh_client)

    assert len(results) == 2
    assert results[0]["prompt"] == "Hello world"
    assert results[0]["response"] == "Cleaned Output"
    mock_ssh_client.exec_command.assert_called()


def test_run_batch_missing_prompt_column(tmp_path, mock_ssh_client):
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("wrong_header\nTest\n", encoding='utf-8')

    with pytest.raises(ValueError, match="CSV file must contain a 'prompt' column"):
        run_batch(str(csv_path), "llama2", ssh_client=mock_ssh_client)


def test_run_batch_without_ssh():
    with pytest.raises(ValueError, match="SSH client required"):
        run_batch("somefile.csv", "llama2", ssh_client=None)


# --------- Tests for run_prompts_from_csv (interactive) ---------

@mock.patch("builtins.input", return_value="exit")
def test_run_prompts_from_csv_user_exit(mock_input, mock_ssh_client):
    result = run_prompts_from_csv(mock_ssh_client, "llama2")
    assert result is False


@mock.patch("batch_runner.run_batch")
@mock.patch("builtins.input")
def test_run_prompts_from_csv_success(mock_input, mock_run_batch, tmp_path, mock_ssh_client):
    # Prepare dummy CSV
    csv_file = tmp_path / "input.csv"
    csv_file.write_text("prompt\nHello\n", encoding='utf-8')
    mock_input.return_value = str(csv_file)

    # Mock run_batch return
    mock_run_batch.return_value = [{"prompt": "Hello", "response": "Hi"}]

    result = run_prompts_from_csv(mock_ssh_client, "llama2")

    assert result is True

    # Check if result file was created
    output_file = tmp_path / "input_results.csv"
    assert output_file.exists()
    assert "response" in output_file.read_text()


@mock.patch("builtins.input", return_value="bad_file.csv")
def test_run_prompts_from_csv_file_not_found(mock_input, mock_ssh_client):
    result = run_prompts_from_csv(mock_ssh_client, "llama2")
    assert result is False
