import pytest
from llm_utils import clean_ollama_output

def test_clean_ollama_output_strips_whitespace():
    raw = "   Test response with spaces \n"
    cleaned = clean_ollama_output(raw)
    assert cleaned == "Test response with spaces"

def test_clean_text_empty():
    assert clean_ollama_output("") == ""
