"""
User input prompts.

Consolidated from various modules with consistent interface.
"""

import getpass
from typing import List, Optional, Any
from pathlib import Path
from amp_llm.cli.prompts import ainput, aprint

try:
    from aioconsole import ainput, aprint
except ImportError:
    async def ainput(prompt):
        return input(prompt)
    async def aprint(*args, **kwargs):
        print(*args, **kwargs)

from colorama import Fore, Style

from .formatters import colorize, info, error
from .validators import validate_file_path
from .exceptions import UserCancelled, ValidationError


# =============================================================================
# Basic Prompts
# =============================================================================

async def prompt_text(
    message: str,
    default: Optional[str] = None,
    required: bool = False,
    validator: Optional[callable] = None,
) -> str:
    """
    Prompt for text input.
    
    Args:
        message: Prompt message
        default: Default value
        required: Whether input is required
        validator: Optional validation function
    
    Returns:
        User input
    
    Raises:
        UserCancelled: If user cancels (Ctrl+C)
        ValidationError: If validation fails
    
    Example:
        >>> name = await prompt_text("Enter your name", required=True)
        >>> email = await prompt_text("Email", validator=validate_email)
    """
    # Format prompt
    prompt = f"{Fore.CYAN}{message}"
    if default:
        prompt += f" [{default}]"
    prompt += f": {Style.RESET_ALL}"
    
    while True:
        try:
            value = await ainput(prompt)
            value = value.strip()
            
            # Use default if empty
            if not value and default:
                value = default
            
            # Check required
            if required and not value:
                await aprint(error("This field is required"))
                continue
            
            # Validate
            if validator and value:
                is_valid, error_msg = validator(value)
                if not is_valid:
                    await aprint(error(error_msg))
                    continue
            
            return value
            
        except KeyboardInterrupt:
            raise UserCancelled("Input cancelled by user")


async def prompt_choice(
    message: str,
    choices: List[str],
    default: Optional[str] = None,
    allow_custom: bool = False,
) -> str:
    """
    Prompt for choice from list.
    
    Args:
        message: Prompt message
        choices: List of valid choices
        default: Default choice
        allow_custom: Allow custom input not in choices
    
    Returns:
        Selected choice
    
    Example:
        >>> color = await prompt_choice("Choose color", ["red", "green", "blue"])
        >>> fruit = await prompt_choice("Fruit", ["apple", "banana"], default="apple")
    """
    # Display choices
    await aprint(f"\n{Fore.CYAN}{message}:")
    for i, choice in enumerate(choices, 1):
        marker = "*" if choice == default else " "
        await aprint(f"  {marker} {i}) {choice}")
    
    # Prompt
    prompt_msg = "Enter choice"
    if default:
        prompt_msg += f" [{default}]"
    
    while True:
        choice = await prompt_text(prompt_msg)
        
        # Use default if empty
        if not choice and default:
            return default
        
        # Check if it's a number
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(choices):
                return choices[idx]
        
        # Check if it matches a choice
        choice_lower = choice.lower()
        for valid_choice in choices:
            if valid_choice.lower() == choice_lower:
                return valid_choice
        
        # Check if custom input allowed
        if allow_custom:
            return choice
        
        await aprint(error(f"Invalid choice. Please choose from: {', '.join(choices)}"))


async def prompt_confirm(
    message: str,
    default: bool = False,
) -> bool:
    """
    Prompt for yes/no confirmation.
    
    Args:
        message: Confirmation message
        default: Default answer
    
    Returns:
        True if yes, False if no
    
    Example:
        >>> if await prompt_confirm("Continue?", default=True):
        ...     print("Continuing...")
    """
    default_str = "Y/n" if default else "y/N"
    prompt = f"{Fore.CYAN}{message} [{default_str}]: {Style.RESET_ALL}"
    
    while True:
        try:
            response = await ainput(prompt)
            response = response.strip().lower()
            
            if not response:
                return default
            
            if response in ('y', 'yes'):
                return True
            elif response in ('n', 'no'):
                return False
            else:
                await aprint(error("Please answer 'yes' or 'no'"))
                
        except KeyboardInterrupt:
            raise UserCancelled("Confirmation cancelled")


async def prompt_password(
    message: str = "Password",
    confirm: bool = False,
) -> str:
    """
    Prompt for password (hidden input).
    
    Args:
        message: Prompt message
        confirm: Whether to ask for confirmation
    
    Returns:
        Password string
    
    Raises:
        ValidationError: If passwords don't match
    
    Example:
        >>> password = await prompt_password(confirm=True)
    """
    await aprint(f"{Fore.CYAN}{message}: ", end='')
    password = getpass.getpass('')
    
    if confirm:
        await aprint(f"{Fore.CYAN}Confirm {message}: ", end='')
        password2 = getpass.getpass('')
        
        if password != password2:
            raise ValidationError("Passwords do not match")
    
    return password


# =============================================================================
# Advanced Prompts
# =============================================================================

async def prompt_multiline(
    message: str,
    end_marker: str = "<<<end",
) -> str:
    """
    Prompt for multiline input.
    
    Args:
        message: Prompt message
        end_marker: Marker to end input
    
    Returns:
        Combined multiline input
    
    Example:
        >>> text = await prompt_multiline("Enter JSON")
        >>> # User types multiple lines, then "<<<end"
    """
    await aprint(f"\n{Fore.YELLOW}{message}")
    await aprint(f"{Fore.YELLOW}(Type '{end_marker}' on a new line to finish)")
    await aprint(f"{Style.RESET_ALL}")
    
    lines = []
    try:
        while True:
            line = await ainput('')
            if line.strip().lower() == end_marker:
                break
            lines.append(line)
    except KeyboardInterrupt:
        raise UserCancelled("Multiline input cancelled")
    
    return '\n'.join(lines)


async def prompt_file(
    message: str,
    must_exist: bool = True,
    file_type: Optional[str] = None,
) -> Path:
    """
    Prompt for file path.
    
    Args:
        message: Prompt message
        must_exist: Whether file must already exist
        file_type: Expected file extension (e.g., ".json")
    
    Returns:
        Path object
    
    Raises:
        ValidationError: If file doesn't exist or wrong type
    
    Example:
        >>> file_path = await prompt_file("Select JSON file", file_type=".json")
    """
    while True:
        path_str = await prompt_text(message)
        
        if not path_str:
            continue
        
        path = Path(path_str)
        
        # Check if exists
        if must_exist and not path.exists():
            await aprint(error(f"File not found: {path}"))
            continue
        
        # Check file type
        if file_type and not path.suffix.lower() == file_type.lower():
            await aprint(error(f"File must be {file_type} type"))
            continue
        
        return path


async def prompt_number(
    message: str,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    default: Optional[float] = None,
    integer: bool = False,
) -> float:
    """
    Prompt for numeric input.
    
    Args:
        message: Prompt message
        min_value: Minimum allowed value
        max_value: Maximum allowed value
        default: Default value
        integer: Whether to require integer
    
    Returns:
        Numeric value
    
    Example:
        >>> age = await prompt_number("Enter age", min_value=0, max_value=150, integer=True)
        >>> ratio = await prompt_number("Enter ratio", min_value=0.0, max_value=1.0)
    """
    def validator(value_str: str) -> tuple[bool, str]:
        try:
            if integer:
                value = int(value_str)
            else:
                value = float(value_str)
            
            if min_value is not None and value < min_value:
                return False, f"Value must be >= {min_value}"
            
            if max_value is not None and value > max_value:
                return False, f"Value must be <= {max_value}"
            
            return True, ""
        except ValueError:
            return False, f"Must be a valid {'integer' if integer else 'number'}"
    
    value_str = await prompt_text(
        message,
        default=str(default) if default is not None else None,
        required=True,
        validator=validator,
    )
    
    return int(value_str) if integer else float(value_str)


async def prompt_list(
    message: str,
    separator: str = ",",
    strip: bool = True,
) -> List[str]:
    """
    Prompt for list of items (comma-separated).
    
    Args:
        message: Prompt message
        separator: Item separator
        strip: Whether to strip whitespace from items
    
    Returns:
        List of items
    
    Example:
        >>> ncts = await prompt_list("Enter NCT numbers (comma-separated)")
        >>> # User enters: NCT12345, NCT67890, NCT11111
        >>> print(ncts)
        ['NCT12345', 'NCT67890', 'NCT11111']
    """
    text = await prompt_text(message)
    
    if not text:
        return []
    
    items = text.split(separator)
    
    if strip:
        items = [item.strip() for item in items]
    
    # Remove empty items
    items = [item for item in items if item]
    
    return items