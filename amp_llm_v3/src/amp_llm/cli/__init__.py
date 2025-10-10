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

from .commands import CommandRegistry, Command
from .parser import CLIParser, Argument, Option
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
from .prompts import (
    prompt_text,
    prompt_choice,
    prompt_confirm,
    prompt_password,
    prompt_multiline,
    prompt_file,
)
from .progress import (
    Spinner,
    ProgressBar,
    IndeterminateProgress,
)
from .output import (
    OutputManager,
    ConsoleOutput,
    FileOutput,
    format_bytes,
    format_duration,
    format_timestamp,
)
from .validators import (
    validate_email,
    validate_url,
    validate_nct_number,
    validate_file_path,
    validate_ip_address,
)
from .exceptions import (
    CLIError,
    CommandError,
    ValidationError,
    UserCancelled,
)

__all__ = [
    # Commands
    'CommandRegistry',
    'Command',
    
    # Parser
    'CLIParser',
    'Argument',
    'Option',
    
    # Formatters
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