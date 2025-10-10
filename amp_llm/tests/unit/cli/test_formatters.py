"""
tests/unit/cli/test_formatters.py
"""

import pytest
from amp_llm.src.cli import format_table, format_list, colorize


def test_format_table_basic():
    """Test basic table formatting."""
    data = [
        {"name": "Alice", "age": 30},
        {"name": "Bob", "age": 25},
    ]
    
    result = format_table(data)
    
    assert "Alice" in result
    assert "Bob" in result
    assert "30" in result
    assert "25" in result


def test_format_list_numbered():
    """Test numbered list formatting."""
    items = ["First", "Second", "Third"]
    result = format_list(items, style="numbered")
    
    assert "1. First" in result
    assert "2. Second" in result
    assert "3. Third" in result


def test_colorize():
    """Test text colorization."""
    from colorama import Fore, Style
    
    result = colorize("Test", "green", bold=True)
    
    assert Fore.GREEN in result
    assert Style.BRIGHT in result
    assert "Test" in result