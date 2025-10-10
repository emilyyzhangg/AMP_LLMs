import json
from typing import Dict, Any, Optional

# =============================================================================
# Dictionary Formatting
# =============================================================================

def format_dict(
    data: Dict[str, Any],
    indent: int = 0,
    max_value_length: Optional[int] = 80,
) -> str:
    """
    Format dictionary with key-value pairs.
    
    Args:
        data: Dictionary to format
        indent: Indentation level
        max_value_length: Maximum value length before truncation
    
    Returns:
        Formatted string
    """
    lines = []
    indent_str = "  " * indent
    
    # Calculate max key length for alignment
    max_key_len = max(len(str(k)) for k in data.keys()) if data else 0
    
    for key, value in data.items():
        key_str = str(key).ljust(max_key_len)
        value_str = str(value)
        
        # Truncate long values
        if max_value_length and len(value_str) > max_value_length:
            value_str = value_str[:max_value_length - 3] + "..."
        
        lines.append(
            f"{indent_str}{colorize(key_str, 'cyan')}: {value_str}"
        )
    
    return "\n".join(lines)


# =============================================================================
# JSON Formatting
# =============================================================================

def format_json(data: Any, indent: int = 2, compact: bool = False) -> str:
    """
    Format data as pretty JSON.
    
    Args:
        data: Data to format
        indent: Indentation spaces
        compact: Whether to use compact format
    
    Returns:
        JSON string
    """
    if compact:
        return json.dumps(data, ensure_ascii=False)
    else:
        return json.dumps(data, indent=indent, ensure_ascii=False)