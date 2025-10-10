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
