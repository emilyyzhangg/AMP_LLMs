import pytest
from unittest import mock
from llm_runner import run_llm_prompt, summarize_study, run_llm_workflow

# ------------------------
# Test: run_llm_prompt
# ------------------------

def test_run_llm_prompt_calls_run_ollama():
    mock_ssh = mock.Mock()
    mock_model = "llama2"
    mock_prompt = "Tell me a joke"

    with mock.patch("llm_runner.run_ollama", return_value="Sure, here's one!") as mock_run:
        response = run_llm_prompt(mock_ssh, mock_model, mock_prompt)

    mock_run.assert_called_once_with(mock_ssh, mock_model, mock_prompt)
    assert response == "Sure, here's one!"

# ------------------------
# Test: summarize_study
# ------------------------

def test_summarize_study_valid():
    mock_ssh = mock.Mock()
    model = "llama2"
    study_info = {
        "pmid": "12345",
        "title": "Study Title",
        "authors": ["Alice", "Bob"],
        "journal": "Science",
        "publication_date": "2020-01-01",
        "abstract": "This is an abstract."
    }

    with mock.patch("llm_runner.run_ollama", return_value="Summary of study.") as mock_run:
        result = summarize_study(mock_ssh, model, study_info)

    assert "Summary of study" in result
    mock_run.assert_called_once()
    args = mock_run.call_args[0]
    assert study_info["title"] in args[2]  # Prompt argument

def test_summarize_study_missing_info():
    result = summarize_study(mock.Mock(), "llama2", {"error": "Not found"})
    assert result == "No study info available to summarize."

# ------------------------
# Test: run_llm_workflow
# ------------------------

@mock.patch("llm_runner.check_ollama_installed")
@mock.patch("llm_runner.get_available_models", return_value=["llama2"])
@mock.patch("llm_runner.choose_model", return_value="llama2")
@mock.patch("llm_runner.ensure_model_available")
@mock.patch("llm_runner.fetch_pubmed_study", return_value={"title": "Test", "abstract": "Test abstract"})
@mock.patch("llm_runner.interactive_session")
@mock.patch("llm_runner.input")
def test_run_llm_workflow_interactive(
    mock_input, mock_interactive, mock_fetch, mock_ensure, mock_choose, mock_get_models, mock_check
):
    mock_input.side_effect = [
        "12345",  # PubMed ID
        "1",      # Mode: Interactive session
        "3"       # Mode: Exit
    ]

    ssh_client = mock.Mock()

    run_llm_workflow(ssh_client)

    mock_check.assert_called_once()
    mock_get_models.assert_called_once()
    mock_choose.assert_called_once()
    mock_ensure.assert_called_once()
    mock_fetch.assert_called_once_with("12345")
    mock_interactive.assert_called_once()

@mock.patch("llm_runner.check_ollama_installed", side_effect=Exception("SSH failed"))
def test_run_llm_workflow_fails_ollama_check(mock_check):
    ssh_client = mock.Mock()
    run_llm_workflow(ssh_client)  # Should print error and return cleanly
    mock_check.assert_called_once()

@mock.patch("llm_runner.get_available_models", return_value=[])
@mock.patch("llm_runner.check_ollama_installed")
def test_run_llm_workflow_no_models(mock_check, mock_models):
    ssh_client = mock.Mock()
    run_llm_workflow(ssh_client)
    mock_models.assert_called_once()
