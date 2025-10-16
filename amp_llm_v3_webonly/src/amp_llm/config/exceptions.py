"""
Custom exceptions for configuration module.
"""


class ConfigError(Exception):
    """Base exception for configuration errors."""
    pass


class ValidationError(ConfigError):
    """Raised when configuration validation fails."""
    pass


class LoggingError(ConfigError):
    """Raised when logging configuration fails."""
    pass


class SettingsError(ConfigError):
    """Raised when settings cannot be loaded or are invalid."""
    pass