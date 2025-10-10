"""
Output formatting utilities.

Provides functions for formatting data as tables, lists, JSON, etc.
with colors and styles.
"""

import json
from typing import List, Dict, Any, Optional, Union
from datetime import datetime
from colorama import Fore, Style, Back


# =============================================================================
# Color Utilities
# =============================================================================

def colorize(text: str, color: str, bold: bool = False, bg: Optional[str] = None) -> str:
    """
    Apply color to text.
    
    Args:
        text: Text to colorize
        color: Color name (red, green, yellow, blue, magenta, cyan, white)
        bold: Whether to make text bold
        bg: Background color (optional)
    
    Returns:
        Colorized text
    
    Example:
        >>> print(colorize("Hello", "green", bold=True))
    """
    color_map = {
        'red': Fore.RED,
        'green': Fore.GREEN,
        'yellow': Fore.YELLOW,
        'blue': Fore.BLUE,
        'magenta': Fore.MAGENTA,
        'cyan': Fore.CYAN,
        'white': Fore.WHITE,
    }
    
    bg_map = {
        'red': Back.RED,
        'green': Back.GREEN,
        'yellow': Back.YELLOW,
        'blue': Back.BLUE,
        'magenta': Back.MAGENTA,
        'cyan': Back.CYAN,
        'white': Back.WHITE,
    }
    
    result = ""
    
    if bold:
        result += Style.BRIGHT
    
    if color.lower() in color_map:
        result += color_map[color.lower()]
    
    if bg and bg.lower() in bg_map:
        result += bg_map[bg.lower()]
    
    result += text + Style.RESET_ALL
    
    return result


def emphasize(text: str) -> str:
    """Make text emphasized (bright white)."""
    return f"{Style.BRIGHT}{Fore.WHITE}{text}{Style.RESET_ALL}"


def success(text: str) -> str:
    """Format as success message (green)."""
    return f"{Fore.GREEN}✅ {text}{Style.RESET_ALL}"


def warning(text: str) -> str:
    """Format as warning message (yellow)."""
    return f"{Fore.YELLOW}⚠️  {text}{Style.RESET_ALL}"


def error(text: str) -> str:
    """Format as error message (red)."""
    return f"{Fore.RED}❌ {text}{Style.RESET_ALL}"


def info(text: str) -> str:
    """Format as info message (cyan)."""
    return f"{Fore.CYAN}ℹ️  {text}{Style.RESET_ALL}"


# =============================================================================
# Table Formatting
# =============================================================================

def format_table(
    data: List[Dict[str, Any]],
    headers: Optional[List[str]] = None,
    max_width: Optional[int] = None,
    align: Optional[Dict[str, str]] = None,
) -> str:
    """
    Format data as ASCII table.
    
    Args:
        data: List of dictionaries
        headers: Optional header names (defaults to dict keys)
        max_width: Maximum column width
        align: Column alignment (left, right, center)
    
    Returns:
        Formatted table string
    
    Example:
        >>> data = [
        ...     {"name": "Alice", "age": 30, "city": "NYC"},
        ...     {"name": "Bob", "age": 25, "city": "LA"},
        ... ]
        >>> print(format_table(data))
        ┌───────┬─────┬──────┐
        │ Name  │ Age │ City │
        ├───────┼─────┼──────┤
        │ Alice │  30 │ NYC  │
        │ Bob   │  25 │ LA   │
        └───────┴─────┴──────┘
    """
    if not data:
        return "No data to display"
    
    # Get headers
    if headers is None:
        headers = list(data[0].keys())
    
    # Calculate column widths
    col_widths = {}
    for header in headers:
        # Start with header width
        col_widths[header] = len(str(header))
        
        # Check data widths
        for row in data:
            value = str(row.get(header, ""))
            if max_width and len(value) > max_width:
                value = value[:max_width - 3] + "..."
            col_widths[header] = max(col_widths[header], len(value))
    
    # Default alignment
    if align is None:
        align = {header: 'left' for header in headers}
    
    # Build table
    lines = []
    
    # Top border
    lines.append("┌" + "┬".join("─" * (col_widths[h] + 2) for h in headers) + "┐")
    
    # Headers
    header_cells = []
    for header in headers:
        cell = f" {header.title()} "
        # Pad to width
        padding = col_widths[header] - len(header)
        cell = cell + " " * padding
        header_cells.append(cell)
    
    lines.append("│" + "│".join(header_cells) + "│")
    
    # Header separator
    lines.append("├" + "┼".join("─" * (col_widths[h] + 2) for h in headers) + "┤")
    
    # Data rows
    for row in data:
        row_cells = []
        for header in headers:
            value = str(row.get(header, ""))
            
            # Truncate if needed
            if max_width and len(value) > max_width:
                value = value[:max_width - 3] + "..."
            
            # Align
            col_align = align.get(header, 'left')
            if col_align == 'right':
                value = value.rjust(col_widths[header])
            elif col_align == 'center':
                value = value.center(col_widths[header])
            else:  # left
                value = value.ljust(col_widths[header])
            
            row_cells.append(f" {value} ")
        
        lines.append("│" + "│".join(row_cells) + "│")
    
    # Bottom border
    lines.append("└" + "┴".join("─" * (col_widths[h] + 2) for h in headers) + "┘")
    
    return "\n".join(lines)


def format_simple_table(data: List[Dict[str, Any]]) -> str:
    """
    Format data as simple table (no borders).
    
    Args:
        data: List of dictionaries
    
    Returns:
        Formatted table string
    """
    if not data:
        return "No data to display"
    
    headers = list(data[0].keys())
    
    # Calculate column widths
    col_widths = {}
    for header in headers:
        col_widths[header] = len(str(header))
        for row in data:
            col_widths[header] = max(col_widths[header], len(str(row.get(header, ""))))
    
    # Build table
    lines = []
    
    # Headers
    header_line = "  ".join(h.ljust(col_widths[h]) for h in headers)
    lines.append(colorize(header_line, "cyan", bold=True))
    
    # Separator
    lines.append("  ".join("─" * col_widths[h] for h in headers))
    
    # Data
    for row in data:
        row_line = "  ".join(str(row.get(h, "")).ljust(col_widths[h]) for h in headers)
        lines.append(row_line)
    
    return "\n".join(lines)


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


# =============================================================================
# Special Formatting
# =============================================================================

def format_header(text: str, char: str = "=", width: int = 60) -> str:
    """
    Format text as header with border.
    
    Args:
        text: Header text
        char: Border character
        width: Total width
    
    Returns:
        Formatted header
    
    Example:
        >>> print(format_header("Results"))
        ============================================================
        Results
        ============================================================
    """
    lines = [
        char * width,
        text.center(width),
        char * width,
    ]
    return "\n".join(lines)


def format_banner(text: str, width: int = 60) -> str:
    """
    Format text as banner with box border.
    
    Args:
        text: Banner text
        width: Total width
    
    Returns:
        Formatted banner
    """
    lines = [
        "┌" + "─" * (width - 2) + "┐",
        "│" + text.center(width - 2) + "│",
        "└" + "─" * (width - 2) + "┘",
    ]
    return "\n".join(lines)


def format_section(title: str, content: str) -> str:
    """
    Format content with section title.
    
    Args:
        title: Section title
        content: Section content
    
    Returns:
        Formatted section
    """
    return f"\n{colorize(title, 'yellow', bold=True)}\n{content}\n"


def format_key_value_pairs(pairs: Dict[str, Any], separator: str = ": ") -> str:
    """
    Format key-value pairs with consistent alignment.
    
    Args:
        pairs: Dictionary of key-value pairs
        separator: Separator between key and value
    
    Returns:
        Formatted string
    """
    if not pairs:
        return ""
    
    max_key_len = max(len(str(k)) for k in pairs.keys())
    
    lines = []
    for key, value in pairs.items():
        key_str = str(key).ljust(max_key_len)
        lines.append(f"{colorize(key_str, 'cyan')}{separator}{value}")
    
    return "\n".join(lines)