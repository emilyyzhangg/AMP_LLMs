"""
Command-line interface package.

Provides reusable CLI components for user interaction, formatting,
and command execution.

Example:
    >>> from amp_llm.cli import format_table, prompt_choice, Spinner
    >>> 
    >>> # Format data as table
    >>> data = [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]
    >>> print(format_table(data))
    >>> 
    >>> # Prompt user
    >>> choice = await prompt_choice("Select option", ["A", "B", "C"])
    >>> 
    >>> # Show progress
    >>> async with Spinner("Processing..."):
    ...     await do_work()
"""

# Async I/O (single source of truth)
from .async_io import ainput, aprint

# REMOVED: This line is causing the error
# from .commands import CommandRegistry, Command

# Parser (if it exists and doesn't import commands)
try:
    from .parser import CLIParser, Argument, Option
except ImportError:
    CLIParser = None
    Argument = None
    Option = None

# Formatters
try:
    from .formatters import (
        format_table,
        format_list,
        format_dict,
        format_json,
        format_tree,
        colorize,
        emphasize,
        success,
        warning,
        error,
        info,
    )
except ImportError:
    # Formatters not implemented yet
    format_table = None
    format_list = None
    format_dict = None
    format_json = None
    format_tree = None
    colorize = None
    emphasize = None
    success = None
    warning = None
    error = None
    info = None

# Prompts
from .prompts import (
    prompt_text,
    prompt_choice,
    prompt_confirm,
    prompt_password,
    prompt_multiline,
    prompt_file,
)

# Progress
from .progress import (
    Spinner,
    ProgressBar,
    IndeterminateProgress,
)

# Output
from .output import (
    OutputManager,
    ConsoleOutput,
    FileOutput,
    format_bytes,
    format_duration,
    format_timestamp,
)

# Validators
from .validators import (
    validate_email,
    validate_url,
    validate_nct_number,
    validate_file_path,
    validate_ip_address,
)

# Exceptions
from .exceptions import (
    CLIError,
    CommandError,
    ValidationError,
    UserCancelled,
)

__all__ = [
    # Async I/O
    'ainput',
    'aprint',
    
    # Parser (conditional)
    'CLIParser',
    'Argument',
    'Option',
    
    # Formatters (conditional)
    'format_table',
    'format_list',
    'format_dict',
    'format_json',
    'format_tree',
    'colorize',
    'emphasize',
    'success',
    'warning',
    'error',
    'info',
    
    # Prompts
    'prompt_text',
    'prompt_choice',
    'prompt_confirm',
    'prompt_password',
    'prompt_multiline',
    'prompt_file',
    
    # Progress
    'Spinner',
    'ProgressBar',
    'IndeterminateProgress',
    
    # Output
    'OutputManager',
    'ConsoleOutput',
    'FileOutput',
    'format_bytes',
    'format_duration',
    'format_timestamp',
    
    # Validators
    'validate_email',
    'validate_url',
    'validate_nct_number',
    'validate_file_path',
    'validate_ip_address',
    
    # Exceptions
    'CLIError',
    'CommandError',
    'ValidationError',
    'UserCancelled',
]

__version__ = '3.0.0'