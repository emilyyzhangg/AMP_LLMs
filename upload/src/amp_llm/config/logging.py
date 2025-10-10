"""
Logging configuration and utilities.

Extracted from config.py with enhanced features.
"""

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import os

from .exceptions import ConfigError


@dataclass
class LogConfig:
    """
    Logging configuration.
    
    Attributes:
        log_file: Path to log file
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Log message format
        date_format: Timestamp format
        enable_console: Whether to log to console/stdout
        enable_file: Whether to log to file
        max_bytes: Maximum log file size before rotation (0 = no rotation)
        backup_count: Number of backup log files to keep
    """
    log_file: Path = field(default_factory=lambda: Path('amp_llm.log'))
    log_level: str = field(default_factory=lambda: os.getenv('LOG_LEVEL', 'INFO'))
    log_format: str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    date_format: str = '%Y-%m-%d %H:%M:%S'
    enable_console: bool = True
    enable_file: bool = True
    max_bytes: int = 10 * 1024 * 1024  # 10 MB
    backup_count: int = 5
    
    def validate(self) -> list[str]:
        """Validate logging configuration."""
        errors = []
        
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if self.log_level.upper() not in valid_levels:
            errors.append(
                f"Invalid log level: {self.log_level} "
                f"(must be one of: {', '.join(valid_levels)})"
            )
        
        if not self.enable_console and not self.enable_file:
            errors.append("At least one of enable_console or enable_file must be True")
        
        if self.max_bytes < 0:
            errors.append(f"Invalid max_bytes: {self.max_bytes} (cannot be negative)")
        
        if self.backup_count < 0:
            errors.append(f"Invalid backup_count: {self.backup_count}")
        
        return errors


# =============================================================================
# Logging Setup
# =============================================================================

_logging_configured = False


def setup_logging(config: Optional[LogConfig] = None) -> None:
    """
    Configure application-wide logging.
    
    This should be called once at application startup.
    
    Args:
        config: Logging configuration (uses defaults if None)
    
    Raises:
        ConfigError: If logging configuration is invalid
    
    Example:
        >>> from amp_llm.config import setup_logging, LogConfig
        >>> config = LogConfig(log_level='DEBUG')
        >>> setup_logging(config)
    """
    global _logging_configured
    
    if _logging_configured:
        return
    
    if config is None:
        config = LogConfig()
    
    # Validate configuration
    errors = config.validate()
    if errors:
        raise ConfigError(
            f"Invalid logging configuration:\n  - " + "\n  - ".join(errors)
        )
    
    # Get log level
    log_level = getattr(logging, config.log_level.upper())
    
    # Create formatters
    formatter = logging.Formatter(
        fmt=config.log_format,
        datefmt=config.date_format
    )
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remove existing handlers
    root_logger.handlers.clear()
    
    # Console handler
    if config.enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
    
    # File handler
    if config.enable_file:
        # Ensure log directory exists
        config.log_file.parent.mkdir(exist_ok=True, parents=True)
        
        if config.max_bytes > 0:
            # Use rotating file handler
            from logging.handlers import RotatingFileHandler
            file_handler = RotatingFileHandler(
                config.log_file,
                maxBytes=config.max_bytes,
                backupCount=config.backup_count,
                encoding='utf-8'
            )
        else:
            # Use regular file handler
            file_handler = logging.FileHandler(
                config.log_file,
                encoding='utf-8'
            )
        
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    # Configure asyncssh to be less verbose
    logging.getLogger('asyncssh').setLevel(logging.WARNING)
    
    # Configure aiohttp to be less verbose
    logging.getLogger('aiohttp').setLevel(logging.WARNING)
    
    _logging_configured = True
    
    # Log initial message
    root_logger.info(f"Logging configured: level={config.log_level}, file={config.log_file}")


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a module.
    
    Automatically sets up logging if not already configured.
    
    Args:
        name: Logger name (typically __name__)
    
    Returns:
        Logger instance
    
    Example:
        >>> from amp_llm.config import get_logger
        >>> logger = get_logger(__name__)
        >>> logger.info("Application started")
    """
    global _logging_configured
    
    if not _logging_configured:
        # Auto-setup with defaults
        try:
            # Try to get settings from Settings
            from .settings import get_settings
            settings = get_settings()
            log_config = LogConfig(
                log_file=settings.paths.log_file,
                log_level=os.getenv('LOG_LEVEL', 'INFO')
            )
            setup_logging(log_config)
        except Exception:
            # Fallback to basic config
            setup_logging()
    
    return logging.getLogger(name)


def set_log_level(level: str) -> None:
    """
    Change logging level at runtime.
    
    Args:
        level: New log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    
    Example:
        >>> from amp_llm.config import set_log_level
        >>> set_log_level('DEBUG')
    """
    valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
    level_upper = level.upper()
    
    if level_upper not in valid_levels:
        raise ValueError(
            f"Invalid log level: {level} (must be one of: {', '.join(valid_levels)})"
        )
    
    log_level = getattr(logging, level_upper)
    
    # Update all handlers
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    for handler in root_logger.handlers:
        handler.setLevel(log_level)
    
    root_logger.info(f"Log level changed to {level_upper}")


def disable_library_logging(library_names: list[str]) -> None:
    """
    Disable or reduce logging for noisy libraries.
    
    Args:
        library_names: List of library names to silence
    
    Example:
        >>> from amp_llm.config import disable_library_logging
        >>> disable_library_logging(['asyncssh', 'aiohttp', 'urllib3'])
    """
    for library_name in library_names:
        logging.getLogger(library_name).setLevel(logging.WARNING)


# =============================================================================
# Context Managers
# =============================================================================

class TemporaryLogLevel:
    """
    Context manager for temporarily changing log level.
    
    Example:
        >>> from amp_llm.config import get_logger, TemporaryLogLevel
        >>> logger = get_logger(__name__)
        >>> 
        >>> with TemporaryLogLevel('DEBUG'):
        ...     logger.debug("This will be logged")
        >>> 
        >>> logger.debug("This won't be logged (if original level was INFO)")
    """
    
    def __init__(self, level: str):
        self.level = level
        self.original_level = None
    
    def __enter__(self):
        root_logger = logging.getLogger()
        self.original_level = root_logger.level
        set_log_level(self.level)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        root_logger = logging.getLogger()
        root_logger.setLevel(self.original_level)
        for handler in root_logger.handlers:
            handler.setLevel(self.original_level)


# =============================================================================
# Utility Functions
# =============================================================================

def log_function_call(logger: logging.Logger):
    """
    Decorator to log function calls.
    
    Example:
        >>> from amp_llm.config import get_logger, log_function_call
        >>> logger = get_logger(__name__)
        >>> 
        >>> @log_function_call(logger)
        ... async def fetch_data(url):
        ...     pass
    """
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            logger.debug(f"Calling {func.__name__} with args={args}, kwargs={kwargs}")
            try:
                result = await func(*args, **kwargs)
                logger.debug(f"{func.__name__} completed successfully")
                return result
            except Exception as e:
                logger.error(f"{func.__name__} raised {type(e).__name__}: {e}")
                raise
        
        def sync_wrapper(*args, **kwargs):
            logger.debug(f"Calling {func.__name__} with args={args}, kwargs={kwargs}")
            try:
                result = func(*args, **kwargs)
                logger.debug(f"{func.__name__} completed successfully")
                return result
            except Exception as e:
                logger.error(f"{func.__name__} raised {type(e).__name__}: {e}")
                raise
        
        # Check if function is async
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator