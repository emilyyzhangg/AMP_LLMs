"""
Input validation utilities.
"""

import re
from pathlib import Path
from typing import Tuple


def validate_email(email: str) -> Tuple[bool, str]:
    """
    Validate email address.
    
    Args:
        email: Email address to validate
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    if re.match(pattern, email):
        return True, ""
    else:
        return False, "Invalid email address format"


def validate_url(url: str) -> Tuple[bool, str]:
    """
    Validate URL.
    
    Args:
        url: URL to validate
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    pattern = r'^https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}.*$'
    
    if re.match(pattern, url):
        return True, ""
    else:
        return False, "Invalid URL format (must start with http:// or https://)"


def validate_nct_number(nct: str) -> Tuple[bool, str]:
    """
    Validate NCT (ClinicalTrials.gov) number.
    
    Args:
        nct: NCT number to validate
    
    Returns:
        Tuple of (is_valid, error_message)
    
    Example:
        >>> validate_nct_number("NCT12345678")
        (True, "")
        >>> validate_nct_number("invalid")
        (False, "NCT number must match format: NCT########")
    """
    pattern = r'^NCT\d{8}$'
    
    if re.match(pattern, nct.upper()):
        return True, ""
    else:
        return False, "NCT number must match format: NCT########"


def validate_file_path(path: str, must_exist: bool = True) -> Tuple[bool, str]:
    """
    Validate file path.
    
    Args:
        path: File path to validate
        must_exist: Whether file must exist
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        p = Path(path)
        
        if must_exist and not p.exists():
            return False, f"File does not exist: {path}"
        
        if must_exist and not p.is_file():
            return False, f"Path is not a file: {path}"
        
        return True, ""
    except Exception as e:
        return False, f"Invalid path: {e}"


def validate_ip_address(ip: str) -> Tuple[bool, str]:
    """
    Validate IP address (IPv4).
    
    Args:
        ip: IP address to validate
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
    
    if not re.match(pattern, ip):
        return False, "Invalid IP address format"
    
    # Check each octet
    octets = ip.split('.')
    for octet in octets:
        value = int(octet)
        if not 0 <= value <= 255:
            return False, f"Invalid IP address: octet {octet} out of range (0-255)"
    
    return True, ""


def validate_port(port: str) -> Tuple[bool, str]:
    """
    Validate port number.
    
    Args:
        port: Port number to validate
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        port_int = int(port)
        if 1 <= port_int <= 65535:
            return True, ""
        else:
            return False, "Port must be between 1 and 65535"
    except ValueError:
        return False, "Port must be a number"


def validate_range(
    value: str,
    min_value: float,
    max_value: float,
    value_type: type = float,
) -> Tuple[bool, str]:
    """
    Validate value is within range.
    
    Args:
        value: Value to validate
        min_value: Minimum allowed value
        max_value: Maximum allowed value
        value_type: Type to convert to (int or float)
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        num = value_type(value)
        if min_value <= num <= max_value:
            return True, ""
        else:
            return False, f"Value must be between {min_value} and {max_value}"
    except ValueError:
        return False, f"Value must be a {value_type.__name__}"


def validate_length(
    value: str,
    min_length: Optional[int] = None,
    max_length: Optional[int] = None,
) -> Tuple[bool, str]:
    """
    Validate string length.
    
    Args:
        value: String to validate
        min_length: Minimum length
        max_length: Maximum length
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    length = len(value)
    
    if min_length is not None and length < min_length:
        return False, f"Must be at least {min_length} characters"
    
    if max_length is not None and length > max_length:
        return False, f"Must be at most {max_length} characters"
    
    return True, ""