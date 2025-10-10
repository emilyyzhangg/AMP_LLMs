"""
CLI-specific exceptions.
"""


class CLIError(Exception):
    """Base exception for CLI errors."""
    pass


class CommandError(CLIError):
    """Raised when command execution fails."""
    pass


class ParsingError(CLIError):
    """Raised when argument parsing fails."""
    pass


class ValidationError(CLIError):
    """Raised when input validation fails."""
    pass


class UserCancelled(CLIError):
    """Raised when user cancels operation."""
    pass


class OutputError(CLIError):
    """Raised when output operation fails."""
    pass