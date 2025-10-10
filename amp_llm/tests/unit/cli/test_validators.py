"""
tests/unit/cli/test_validators.py
"""

import pytest
from amp_llm.src.cli import (
    validate_email,
    validate_nct_number,
    validate_ip_address,
)


def test_validate_email_valid():
    """Test email validation with valid email."""
    is_valid, _ = validate_email("user@example.com")
    assert is_valid is True


def test_validate_email_invalid():
    """Test email validation with invalid email."""
    is_valid, error = validate_email("invalid_email")
    assert is_valid is False
    assert "Invalid email" in error


def test_validate_nct_number_valid():
    """Test NCT number validation."""
    is_valid, _ = validate_nct_number("NCT12345678")
    assert is_valid is True


def test_validate_nct_number_invalid():
    """Test NCT number validation with invalid format."""
    is_valid, error = validate_nct_number("NCT123")
    assert is_valid is False
    assert "NCT########" in error


def test_validate_ip_address_valid():
    """Test IP address validation."""
    is_valid, _ = validate_ip_address("192.168.1.1")
    assert is_valid is True


def test_validate_ip_address_invalid():
    """Test IP address validation with invalid IP."""
    is_valid, _ = validate_ip_address("999.999.999.999")
    assert is_valid is False