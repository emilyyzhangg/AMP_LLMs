"""
Core-specific exceptions.
"""


class CoreError(Exception):
    """Base exception for core package errors."""
    pass


class ApplicationError(CoreError):
    """Raised when application-level errors occur."""
    pass


class MenuError(CoreError):
    """Raised when menu system errors occur."""
    pass


class SSHError(CoreError):
    """Raised when SSH-related errors occur."""
    pass


class SSHConnectionError(SSHError):
    """Raised when SSH connection fails."""
    pass


class SSHAuthenticationError(SSHError):
    """Raised when SSH authentication fails."""
    pass


class LifecycleError(CoreError):
    """Raised when lifecycle management errors occur."""
    pass


class GracefulExit(SystemExit):
    """
    Exception for graceful application exit.
    
    Allows cleanup handlers to run before termination.
    """
    
    def __init__(self, message: str = "Application exiting gracefully", code: int = 0):
        self.message = message
        self.code = code
        super().__init__(code)