import pytest
from unittest import mock
from interactive import (
    clean_ollama_output,
    fetch_pubmed_study,
    search_web,
    query_ollama,
    interactive_session
)


# -------------------------
# Test: clean_ollama_output
# -------------------------
def test_clean_ollama_output_removes_ansi():
    raw = "\x1b[31mHello World\x1b[0m"
    cleaned = clean_ollama_output(raw)
    assert cleaned == "Hello World"


# -------------------------
# Test: fetch_pubmed_study
# -------------------------
@mock.patch("interactive.requests.get")
def test_fetch_pubmed_study_success(mock_get):
    mock_xml = """
    <PubmedArticleSet>
      <PubmedArticle>
        <MedlineCitation>
          <Article>
            <ArticleTitle>Sample Title</ArticleTitle>
            <Abstract>
              <AbstractText>Test abstract.</AbstractText>
            </Abstract>
            <Journal>
              <Title>Sample Journal</Title>
            </Journal>
            <AuthorList>
              <Author>
                <ForeName>Jane</ForeName>
                <LastName>Doe</LastName>
              </Author>
            </AuthorList>
          </Article>
          <PubDate>
            <Year>2021</Year>
          </PubDate>
        </MedlineCitation>
      </PubmedArticle>
    </PubmedArticleSet>
    """
    mock_get.return_value.status_code = 200
    mock_get.return_value.text = mock_xml

    result = fetch_pubmed_study("123456")
    assert result["title"] == "Sample Title"
    assert "Jane Doe" in result["authors"]
    assert result["abstract"] == "Test abstract."
    assert result["journal"] == "Sample Journal"
    assert result["publication_date"] == "2021"

@mock.patch("interactive.requests.get", side_effect=Exception("Network error"))
def test_fetch_pubmed_study_network_error(mock_get):
    result = fetch_pubmed_study("123")
    assert "error" in result


# -------------------------
# Test: search_web
# -------------------------
@mock.patch('interactive.GoogleSearch')
def test_search_web_returns_snippets(mock_google_search):
    # Setup mock instance and return values
    mock_instance = mock.Mock()
    mock_instance.get_dict.return_value = {
        "organic_results": [
            {"snippet": "Snippet 1"},
            {"snippet": "Snippet 2"},
        ]
    }
    mock_google_search.return_value = mock_instance

    result = search_web("test query")
    assert "Snippet 1" in result
    assert "Snippet 2" in result

# -------------------------
# Test: query_ollama
# -------------------------
@mock.patch("interactive.subprocess.Popen")
def test_query_ollama_output(mock_popen):
    process_mock = mock.Mock()
    attrs = {
        'communicate.return_value': ("Output text", ""),
    }
    process_mock.configure_mock(**attrs)
    mock_popen.return_value = process_mock

    result = query_ollama("llama2", "Tell me something")
    assert "Output text" in result


# -------------------------
# Partial test: interactive_session
# -------------------------
@mock.patch("interactive.query_ollama", return_value="Fake response")
@mock.patch("interactive.input")
@mock.patch("interactive.save_responses_to_excel")
def test_interactive_session_basic_flow(mock_save, mock_input, mock_query):
    mock_input.side_effect = [
        "What is AMP?",  # prompt
        "exit",          # end loop
        "exit"           # skip saving
    ]

    interactive_session(ssh_client=None, model_name="llama2")
    mock_query.assert_called_once()
