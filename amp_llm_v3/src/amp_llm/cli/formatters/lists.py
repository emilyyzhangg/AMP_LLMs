from typing import List, Dict, Any

# =============================================================================
# List Formatting
# =============================================================================

def format_list(
    items: List[Any],
    style: str = "bullet",
    indent: int = 0,
) -> str:
    """
    Format items as list.
    
    Args:
        items: List of items to format
        style: List style (bullet, numbered, dash)
        indent: Indentation level
    
    Returns:
        Formatted list string
    
    Example:
        >>> items = ["Apple", "Banana", "Cherry"]
        >>> print(format_list(items, style="numbered"))
        1. Apple
        2. Banana
        3. Cherry
    """
    lines = []
    indent_str = "  " * indent
    
    for i, item in enumerate(items, 1):
        if style == "bullet":
            prefix = "•"
        elif style == "numbered":
            prefix = f"{i}."
        elif style == "dash":
            prefix = "-"
        else:
            prefix = "•"
        
        lines.append(f"{indent_str}{prefix} {item}")
    
    return "\n".join(lines)


def format_tree(
    data: Dict[str, Any],
    indent: int = 0,
    is_last: bool = True,
) -> str:
    """
    Format dictionary as tree structure.
    
    Args:
        data: Dictionary to format
        indent: Current indentation level
        is_last: Whether this is the last item
    
    Returns:
        Formatted tree string
    
    Example:
        >>> data = {
        ...     "config": {
        ...         "network": {"host": "localhost"},
        ...         "api": {"timeout": 30}
        ...     }
        ... }
        >>> print(format_tree(data))
    """
    lines = []
    items = list(data.items())
    
    for i, (key, value) in enumerate(items):
        is_last_item = (i == len(items) - 1)
        
        # Prefix
        if indent == 0:
            prefix = ""
        elif is_last_item:
            prefix = "  " * (indent - 1) + "└─ "
        else:
            prefix = "  " * (indent - 1) + "├─ "
        
        # Format key
        if isinstance(value, dict):
            lines.append(f"{prefix}{colorize(key, 'cyan', bold=True)}:")
            # Recursively format nested dict
            lines.append(format_tree(value, indent + 1, is_last_item))
        elif isinstance(value, list):
            lines.append(f"{prefix}{colorize(key, 'cyan')}: [{len(value)} items]")
        else:
            lines.append(f"{prefix}{colorize(key, 'cyan')}: {value}")
    
    return "\n".join(lines)